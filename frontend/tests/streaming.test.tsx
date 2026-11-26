/**
 * @file frontend/tests/streaming.test.tsx
 * @description N1 (ADR-040): the draft of the answer in the Nucleo while the
 * model writes it, and the answer spoken sentence by sentence.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Nucleo from "@/components/nucleo/Nucleo";
import { chooseLanguage } from "@/lib/i18n";
import { speakInSentences, splitSentences } from "@/lib/nucleo/voice";

import { FakeEventSource, installEventSource } from "./helpers";

const LIMITS = {
    max_run_cost: 2,
    max_run_seconds: 900,
    max_failed_tool_calls: 10,
    max_files_modified: 20,
    max_subagents: 3,
    monthly_budget: 30,
};

describe("the answer in pieces", () => {
    it("splits into whole sentences, joins the short ones and cuts the long ones", () => {
        expect(
            splitSentences(
                "Ciao! La luce della cucina è accesa. Vuoi altro? Dimmelo pure quando vuoi."
            )
        ).toEqual([
            // Under 40 characters a piece takes the next sentence too.
            "Ciao! La luce della cucina è accesa. Vuoi altro?",
            "Dimmelo pure quando vuoi.",
        ]);
        expect(splitSentences("  ")).toEqual([]);

        const long = `${"parola ".repeat(60)}fine.`;
        const pieces = splitSentences(long);
        expect(pieces.length).toBeGreaterThan(1);
        expect(pieces.every((piece) => piece.length <= 280)).toBe(true);
        expect(pieces.join(" ")).toBe(long.trim());
    });

    it("synthesizes the next piece while one plays, in order", async () => {
        const log: string[] = [];
        let release: () => void = () => undefined;
        const playing = new Promise<void>((resolve) => (release = resolve));

        const done = speakInSentences(
            ["uno.", "due.", "tre."],
            async (piece) => {
                log.push(`synth ${piece}`);
                return { audio_base64: piece, audio_mime: "audio/wav" };
            },
            async (audio) => {
                log.push(`play ${audio}`);
                if (audio === "uno.") {
                    await playing;
                }
            }
        );

        await waitFor(() => expect(log).toContain("synth due."));
        // The second piece is ready before the first has finished playing.
        expect(log).toEqual(["synth uno.", "synth due.", "play uno."]);
        release();
        expect(await done).toBe(3);
        expect(log).toEqual([
            "synth uno.",
            "synth due.",
            "play uno.",
            "synth tre.",
            "play due.",
            "play tre.",
        ]);
    });

    it("stops without audio, or when a newer answer takes over", async () => {
        const play = vi.fn(async () => undefined);
        expect(
            await speakInSentences(
                ["a.", "b."],
                async () => ({ audio_base64: "", audio_mime: "" }),
                play
            )
        ).toBe(0);
        expect(play).not.toHaveBeenCalled();

        let wanted = true;
        const count = await speakInSentences(
            ["a.", "b.", "c."],
            async (piece) => ({ audio_base64: piece, audio_mime: "audio/wav" }),
            async () => {
                wanted = false;
            },
            () => wanted
        );
        expect(count).toBe(1);
    });
});

describe("the draft in the Nucleo", () => {
    beforeEach(() => chooseLanguage("it"));

    it("shows the answer while the model writes it, then the accepted one, spoken piece by piece", async () => {
        installEventSource();
        let answer: (body: unknown) => void = () => undefined;
        const spoken: unknown[] = [];
        const asked: FormData[] = [];

        vi.stubGlobal(
            "fetch",
            vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
                const url = new URL(String(input));
                const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
                if (url.pathname === "/api/orchestrator/ask") {
                    asked.push(init?.body as FormData);
                    return new Promise<Response>(
                        (resolve) => (answer = (body) => resolve(json(body)))
                    );
                }
                if (url.pathname === "/api/voice/speak") {
                    spoken.push(JSON.parse(String(init?.body)));
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

        render(<Nucleo />);
        const stream = FakeEventSource.instances[0];
        act(() => stream.open());

        // A draft with no command waiting is ignored.
        act(() => stream.emit("answer.delta", { text: "altro" }));
        expect(screen.queryByTestId("answer-draft")).not.toBeInTheDocument();

        fireEvent.change(screen.getByRole("textbox", { name: "Comando" }), {
            target: { value: "com'è il tempo?" },
        });
        fireEvent.click(screen.getByRole("button", { name: "INVIA" }));
        await waitFor(() => expect(asked).toHaveLength(1));
        expect(asked[0].get("delivery")).toBe("live");

        act(() => stream.emit("answer.delta", { text: "Domani" }));
        act(() => stream.emit("answer.delta", { text: "Domani piove" }));
        const draft = await screen.findByTestId("answer-draft");
        expect(draft).toHaveTextContent("bozza · in verifica");
        expect(draft).toHaveTextContent("Domani piove");

        // The Critic sent it back: the draft goes.
        act(() => stream.emit("answer.reset", {}));
        expect(screen.queryByTestId("answer-draft")).not.toBeInTheDocument();
        act(() => stream.emit("answer.delta", { text: "Domani piove a Milano." }));
        expect(await screen.findByTestId("answer-draft")).toHaveTextContent(
            "Domani piove a Milano."
        );

        await act(async () =>
            answer({
                transcription: "Domani piove a Milano. Prendi l'ombrello.",
                audio_base64: "",
                audio_mime: "",
                speak: "sentences",
            })
        );

        expect(
            await screen.findByText("Domani piove a Milano. Prendi l'ombrello.")
        ).toBeInTheDocument();
        expect(screen.queryByTestId("answer-draft")).not.toBeInTheDocument();
        await waitFor(() => expect(spoken).toHaveLength(1));
        // One piece at a time; the voice was off here (no audio), so it stopped after the first.
        expect(spoken[0]).toEqual({
            text: "Domani piove a Milano. Prendi l'ombrello.",
            reply_chars: 41,
        });
    });
});
