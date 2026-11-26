/**
 * @file frontend/tests/wake.test.tsx
 * @description N2 (ADR-041): the wake word.
 *
 * - openWakeWord's streaming pipeline, with stand-in models: what each model
 *   receives, when the word model is first asked, the warm-up and the reset;
 * - the microphone resampled to 16 kHz, the trigger and its pause, the end of
 *   a spoken command;
 * - in the Nucleo: listening starts only with a word chosen and the voice
 *   on, the indicator, the word starting a command that ends by itself and
 *   goes to /listen with live delivery, listening paused meanwhile.
 * The real models were checked against openWakeWord itself (ADR-041).
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
    CHUNK,
    CommandEndWatch,
    EMBEDDING,
    FEATURES,
    MEL_BINS,
    MEL_WINDOW,
    Resampler,
    WakePipeline,
    WakeTrigger,
    type WakeModels,
} from "@/lib/nucleo/wake";

import { FakeEventSource, installEventSource } from "./helpers";

const listener = vi.hoisted(() => ({
    options: null as null | {
        word: string;
        threshold: number;
        onWake: () => void;
        onStatus: (status: string, detail?: string) => void;
    },
    pause: vi.fn(),
    resume: vi.fn(),
    stop: vi.fn(),
}));

vi.mock("@/lib/nucleo/wakeListener", () => ({
    startWakeListener: vi.fn(async (options: NonNullable<typeof listener.options>) => {
        listener.options = options;
        options.onStatus("listening");
        return { pause: listener.pause, resume: listener.resume, stop: listener.stop };
    }),
}));

const recorder = vi.hoisted(() => ({ onEnd: null as null | (() => void), started: 0 }));

vi.mock("@/lib/nucleo/audio", async (original) => ({
    ...(await original<typeof import("@/lib/nucleo/audio")>()),
    chime: vi.fn(async () => undefined),
    startRecording: vi.fn(async (_unavailable: string, options: { onEnd?: () => void } = {}) => {
        recorder.started += 1;
        recorder.onEnd = options.onEnd ?? null;
        return {
            level: () => 0,
            stop: async () => new Blob(["voice"], { type: "audio/webm" }),
            cancel: () => undefined,
        };
    }),
}));

// Imported after the mocks.
const { default: Nucleo } = await import("@/components/nucleo/Nucleo");
const { applyInterface, chooseLanguage, resetInterface } = await import("@/lib/i18n");

/** Models that record what they get: mel gives 1 per frame, the score the call count / 10. */
function fakeModels() {
    const calls = { mel: [] as number[], embed: [] as Float32Array[], score: 0 };
    const models: WakeModels = {
        mel: async (samples) => {
            calls.mel.push(samples.length);
            const frames = Math.floor(samples.length / 160) - 3;
            return new Float32Array(frames * MEL_BINS).fill(10);
        },
        embed: async (window) => {
            calls.embed.push(window);
            return new Float32Array(EMBEDDING).fill(calls.embed.length);
        },
        score: async (features) => {
            expect(features.length).toBe(FEATURES * EMBEDDING);
            calls.score += 1;
            return calls.score / 10;
        },
    };
    return { models, calls };
}

describe("the openWakeWord pipeline", () => {
    it("feeds each model what openWakeWord does, and scores after 16 features and the warm-up", async () => {
        const { models, calls } = fakeModels();
        const pipeline = new WakePipeline(models);

        // Half a chunk: nothing yet.
        expect(await pipeline.push(new Float32Array(CHUNK / 2))).toEqual([]);
        expect(await pipeline.push(new Float32Array(CHUNK / 2))).toEqual([0]);
        // The first chunk alone, then each one with the 480 samples before it.
        expect(calls.mel).toEqual([1280]);
        await pipeline.push(new Float32Array(CHUNK));
        expect(calls.mel).toEqual([1280, 1760]);

        // The window: 76 frames, the oldest still the initial ones, the newest transformed (10 / 10 + 2).
        const window = calls.embed[1];
        expect(window.length).toBe(MEL_WINDOW * MEL_BINS);
        expect(window[0]).toBe(1);
        expect(window[window.length - 1]).toBe(3);

        // 16 features are needed (14 more chunks), then 5 scores are zeroed (chunks 16 to 20).
        const scores = await pipeline.push(new Float32Array(CHUNK * 18));
        expect(calls.score).toBe(5);
        expect(scores).toEqual(new Array(18).fill(0));
        const next = await pipeline.push(new Float32Array(CHUNK));
        expect(next).toEqual([0.6]);

        pipeline.reset();
        expect(await pipeline.push(new Float32Array(CHUNK))).toEqual([0]);
        expect(calls.mel.at(-1)).toBe(1280);
    });

    it("resamples the microphone to 16 kHz, int16-scaled", () => {
        const rate = 48000;
        const resampler = new Resampler(rate);
        const second = Float32Array.from(
            { length: rate },
            (_, i) => 0.5 * Math.sin((2 * Math.PI * 440 * i) / rate)
        );
        let out: number[] = [];
        for (let i = 0; i < second.length; i += 128) {
            out = out.concat(Array.from(resampler.process(second.subarray(i, i + 128))));
        }
        expect(out.length).toBe(16000);
        const peak = Math.max(...out.slice(1000));
        expect(peak).toBeGreaterThan(0.49 * 32767);
        expect(peak).toBeLessThanOrEqual(0.5 * 32767 + 1);

        // 44.1 kHz too, and out-of-range samples are clipped.
        const odd = new Resampler(44100).process(new Float32Array(44100).fill(2));
        expect(odd.length).toBe(16000);
        expect(Math.max(...odd)).toBe(32767);
    });

    it("triggers once over the threshold, then stays quiet for a while", () => {
        const trigger = new WakeTrigger(0.5, 2000);
        expect(trigger.hit(0.49, 0)).toBe(false);
        expect(trigger.hit(0.9, 100)).toBe(true);
        expect(trigger.hit(0.9, 180)).toBe(false);
        expect(trigger.hit(0.9, 2100)).toBe(true);
    });

    it("ends a command after silence, when nothing is said, or when it is too long", () => {
        const rules = { silenceMs: 1200, noSpeechMs: 6000, maxMs: 20000, speechLevel: 0.12 };
        const spoken = new CommandEndWatch(0, rules);
        expect(spoken.update(0.3, 500)).toBe(false);
        expect(spoken.update(0.05, 1600)).toBe(false);
        expect(spoken.update(0.05, 1700)).toBe(true);

        const silent = new CommandEndWatch(0, rules);
        expect(silent.update(0.02, 5900)).toBe(false);
        expect(silent.update(0.02, 6000)).toBe(true);

        const long = new CommandEndWatch(0, rules);
        expect(long.update(0.5, 19900)).toBe(false);
        expect(long.update(0.5, 20000)).toBe(true);
    });
});

const LIMITS = {
    max_run_cost: 2,
    max_run_seconds: 900,
    max_failed_tool_calls: 10,
    max_files_modified: 20,
    max_subagents: 3,
    monthly_budget: 30,
};

function iface(word: string, voiceOn = true) {
    return {
        language: "it" as const,
        voice_language_warning: false,
        voice: { enabled: voiceOn, engine: "piper", name: "it_IT-paola-medium", language: "it" },
        wake: { word, label: word === "off" ? "" : "Hey Jarvis", threshold: 0.35 },
    };
}

describe("the wake word in the Nucleo", () => {
    let asked: FormData[] = [];

    beforeEach(() => {
        chooseLanguage("it");
        listener.options = null;
        listener.pause.mockClear();
        listener.resume.mockClear();
        listener.stop.mockClear();
        recorder.onEnd = null;
        recorder.started = 0;
        asked = [];
        installEventSource();
        vi.stubGlobal(
            "fetch",
            vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
                const url = new URL(String(input));
                const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
                if (url.pathname === "/api/orchestrator/listen") {
                    asked.push(init?.body as FormData);
                    return json({
                        heard: "accendi la luce",
                        transcription: "Ho acceso la luce.",
                        audio_base64: "",
                        audio_mime: "",
                        speak: "sentences",
                    });
                }
                if (url.pathname === "/api/voice/speak") {
                    return json({ audio_base64: "", audio_mime: "" });
                }
                if (url.pathname === "/api/runs/live") {
                    return json({ halted: false, halt_reason: null, limits: LIMITS, runs: [] });
                }
                if (url.pathname === "/api/runs/stats") {
                    return json({ budget: { month_spent: 0, monthly_budget: 2 } });
                }
                return json([]);
            })
        );
    });

    afterEach(() => resetInterface());

    it("does not listen with the word off or the voice off", async () => {
        act(() => applyInterface(iface("off")));
        const { unmount } = render(<Nucleo />);
        act(() => FakeEventSource.instances[0].open());
        expect(screen.queryByTestId("wake-status")).not.toBeInTheDocument();
        unmount();

        act(() => applyInterface(iface("hey_jarvis", false)));
        render(<Nucleo />);
        await act(async () => undefined);
        expect(listener.options).toBeNull();
    });

    it("hears the word, records the command until silence and sends it, paused meanwhile", async () => {
        act(() => applyInterface(iface("hey_jarvis")));
        render(<Nucleo />);
        act(() => FakeEventSource.instances[0].open());

        const status = await screen.findByTestId("wake-status");
        expect(status).toHaveTextContent("In ascolto di «Hey Jarvis»");
        expect(listener.options?.word).toBe("hey_jarvis");
        expect(listener.options?.threshold).toBe(0.35);

        await act(async () => listener.options?.onWake());
        expect(recorder.started).toBe(1);
        expect(recorder.onEnd).not.toBeNull();
        expect(screen.getByText("parla ora · finisce quando smetti")).toBeInTheDocument();
        expect(listener.pause).toHaveBeenCalled();

        // The speaker stopped: the command goes, as with the button.
        await act(async () => recorder.onEnd?.());
        await waitFor(() => expect(asked).toHaveLength(1));
        expect(asked[0].get("delivery")).toBe("live");
        expect(await screen.findByText("Ho acceso la luce.")).toBeInTheDocument();
        await waitFor(() => expect(listener.resume).toHaveBeenCalled());

        // Errors are shown where the indicator is.
        act(() => listener.options?.onStatus("error", "HTTP 503"));
        expect(screen.getByTestId("wake-status")).toHaveTextContent(
            "«Hey Jarvis» non disponibile: HTTP 503"
        );
    });

    it("stops listening when the word is turned off", async () => {
        act(() => applyInterface(iface("hey_jarvis")));
        render(<Nucleo />);
        await screen.findByTestId("wake-status");

        act(() => applyInterface(iface("off")));
        await waitFor(() => expect(listener.stop).toHaveBeenCalled());
        expect(screen.queryByTestId("wake-status")).not.toBeInTheDocument();
    });
});
