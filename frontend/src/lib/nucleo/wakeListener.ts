/**
 * @file frontend/src/lib/nucleo/wakeListener.ts
 * @description The wake word in the browser (N2, ADR-041): the microphone,
 * resampled to 16 kHz, through openWakeWord's models on onnxruntime-web.
 *
 * Everything happens in this page: the audio is not recorded, kept or sent
 * anywhere, not even to the backend, until the word is heard. Then the
 * Nucleo records the command as when the microphone button is pressed.
 *
 * The models come from GET /api/voice/wake/{model} (downloaded once by the
 * backend and checked against their SHA-256). onnxruntime-web is loaded only
 * when a word is chosen, single-threaded (no cross-origin isolation needed).
 */

import { fetchApi } from "@/lib/api/client";

import { Resampler, WakePipeline, WakeTrigger, type WakeModels } from "./wake";

export type WakeStatus = "loading" | "listening" | "paused" | "blocked" | "error";

export interface WakeListener {
    /** Stop scoring (while a command is recorded, sent or spoken). */
    pause(): void;
    /** Score again, from fresh audio. */
    resume(): void;
    /** Close the microphone and free the models. */
    stop(): void;
}

export interface WakeOptions {
    /** The word's model name (hey_jarvis, alexa, hey_mycroft, aurora). */
    word: string;
    threshold: number;
    onWake: () => void;
    onStatus: (status: WakeStatus, detail?: string) => void;
}

type Ort = typeof import("onnxruntime-web");

async function modelBytes(name: string): Promise<Uint8Array> {
    const response = await fetchApi(`/api/voice/wake/${encodeURIComponent(name)}`);
    if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
            detail = (await response.json()).detail ?? detail;
        } catch {
            // Not JSON: the status says enough.
        }
        throw new Error(detail);
    }
    return new Uint8Array(await response.arrayBuffer());
}

async function loadModels(
    ort: Ort,
    word: string
): Promise<{ models: WakeModels; release: () => void }> {
    ort.env.wasm.numThreads = 1;
    const [mel, embed, score] = await Promise.all(
        ["melspectrogram", "embedding_model", word].map(async (name) =>
            ort.InferenceSession.create(await modelBytes(name), { executionProviders: ["wasm"] })
        )
    );
    const run = async (session: typeof mel, data: Float32Array, dims: number[]) => {
        const output = await session.run({
            [session.inputNames[0]]: new ort.Tensor("float32", data, dims),
        });
        return output[session.outputNames[0]].data as Float32Array;
    };
    return {
        models: {
            mel: (samples) => run(mel, samples, [1, samples.length]),
            embed: (window) => run(embed, window, [1, 76, 32, 1]),
            score: async (features) => (await run(score, features, [1, 16, 96]))[0],
        },
        release: () => {
            for (const session of [mel, embed, score]) {
                void session.release();
            }
        },
    };
}

// Samples per callback of the audio node: about 85 ms at 48 kHz.
const BLOCK = 4096;
// Behind by more than this (a slow computer): the oldest audio is dropped.
const MAX_BACKLOG = 16000 * 2;

/**
 * Start listening for the word. Resolves once the microphone is open and
 * the models are loaded; rejects when either fails (the reason in the error).
 */
export async function startWakeListener(options: WakeOptions): Promise<WakeListener> {
    const { word, threshold, onWake, onStatus } = options;
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        throw new Error("The microphone is not available in this browser.");
    }
    onStatus("loading");

    const ort = await import("onnxruntime-web/wasm");
    const { models, release } = await loadModels(ort, word);
    let stream: MediaStream;
    try {
        stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
        });
    } catch (error) {
        release();
        throw error;
    }

    const context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    // ScriptProcessorNode rather than an AudioWorklet: a worklet is a module
    // loaded from a URL, which the page's CSP and the static export make
    // fragile; this runs on the page and needs nothing else.
    const processor = context.createScriptProcessor(BLOCK, 1, 1);
    const mute = context.createGain();
    mute.gain.value = 0;
    source.connect(processor);
    processor.connect(mute);
    mute.connect(context.destination);

    let pipeline = new WakePipeline(models);
    // A resume starts a new generation: scores of older audio still being
    // computed are ignored.
    let generation = 0;
    const trigger = new WakeTrigger(threshold);
    let resampler = new Resampler(context.sampleRate);
    let paused = false;
    let stopped = false;
    let queue: Float32Array[] = [];
    let queued = 0;
    let working = false;

    const drain = async () => {
        if (working) {
            return;
        }
        working = true;
        try {
            while (queue.length && !paused && !stopped) {
                const block = queue.shift() as Float32Array;
                queued -= block.length;
                const current = generation;
                for (const score of await pipeline.push(block)) {
                    if (
                        current === generation &&
                        !paused &&
                        !stopped &&
                        trigger.hit(score, performance.now())
                    ) {
                        paused = true;
                        onStatus("paused");
                        onWake();
                    }
                }
            }
        } catch (error) {
            onStatus("error", error instanceof Error ? error.message : String(error));
        } finally {
            working = false;
        }
    };

    processor.onaudioprocess = (event) => {
        if (paused || stopped) {
            return;
        }
        const block = resampler.process(event.inputBuffer.getChannelData(0));
        queue.push(block);
        queued += block.length;
        while (queued > MAX_BACKLOG && queue.length > 1) {
            queued -= (queue.shift() as Float32Array).length;
        }
        void drain();
    };

    const showRunning = () => onStatus(context.state === "running" ? "listening" : "blocked");
    // Browsers keep audio suspended until the page is touched once.
    const unblock = () => {
        void context.resume().then(() => {
            if (!paused && !stopped) {
                showRunning();
            }
        });
    };
    window.addEventListener("pointerdown", unblock);
    window.addEventListener("keydown", unblock);
    try {
        await context.resume();
    } catch {
        // Still suspended: shown as "blocked" until the first touch.
    }
    showRunning();

    return {
        pause: () => {
            if (stopped) {
                return;
            }
            paused = true;
            onStatus("paused");
        },
        resume: () => {
            if (stopped || !paused) {
                return;
            }
            queue = [];
            queued = 0;
            generation += 1;
            pipeline = new WakePipeline(models);
            resampler = new Resampler(context.sampleRate);
            paused = false;
            showRunning();
        },
        stop: () => {
            if (stopped) {
                return;
            }
            stopped = true;
            window.removeEventListener("pointerdown", unblock);
            window.removeEventListener("keydown", unblock);
            processor.onaudioprocess = null;
            source.disconnect();
            processor.disconnect();
            stream.getTracks().forEach((track) => track.stop());
            void context.close();
            release();
        },
    };
}
