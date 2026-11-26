/**
 * @file frontend/src/lib/nucleo/audio.ts
 * @description Audio for the Nucleo: the microphone with its live level,
 * and the spoken reply played through a level meter so the sphere moves
 * with the real voice. After the wake word (N2, ADR-041) the recording ends
 * by itself when the command is over, and a short tone says it is listening.
 */

import { CommandEndWatch } from "./wake";

/** Root mean square of one block of samples. */
export function rms(samples: Float32Array): number {
    let sum = 0;
    for (let i = 0; i < samples.length; i++) {
        sum += samples[i] * samples[i];
    }
    return samples.length ? Math.sqrt(sum / samples.length) : 0;
}

// Speech sits around 0.02–0.15 RMS; this maps it onto 0..1.
const LEVEL_GAIN = 8;

/** A function that reads the analyser's current level, 0..1. */
export function levelMeter(analyser: AnalyserNode): () => number {
    const samples = new Float32Array(analyser.fftSize);
    return () => {
        analyser.getFloatTimeDomainData(samples);
        return Math.min(1, rms(samples) * LEVEL_GAIN);
    };
}

const silence = () => 0;

export interface Recording {
    level: () => number;
    /** Stop and return what was recorded. */
    stop: () => Promise<Blob>;
    /** Stop and throw the recording away. */
    cancel: () => void;
}

export interface RecordingOptions {
    /** Called once when the command is over (silence after speech, or nothing said). */
    onEnd?: () => void;
}

// How often the level is read to find the end of a command.
const END_POLL_MS = 100;

/** Open the microphone and start recording. Rejects when it is refused. */
export async function startRecording(
    unavailable = "The microphone is not available in this browser.",
    options: RecordingOptions = {},
): Promise<Recording> {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        throw new Error(unavailable);
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    context.createMediaStreamSource(stream).connect(analyser);

    const recorder = new MediaRecorder(stream);
    const chunks: BlobPart[] = [];
    recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
            chunks.push(event.data);
        }
    };
    recorder.start();

    const level = levelMeter(analyser);
    let watching: ReturnType<typeof setInterval> | null = null;
    if (options.onEnd) {
        const onEnd = options.onEnd;
        const watch = new CommandEndWatch(Date.now());
        watching = setInterval(() => {
            if (watch.update(level(), Date.now())) {
                stopWatching();
                onEnd();
            }
        }, END_POLL_MS);
    }
    const stopWatching = () => {
        if (watching) {
            clearInterval(watching);
            watching = null;
        }
    };

    const release = () => {
        stopWatching();
        stream.getTracks().forEach((track) => track.stop());
        void context.close();
    };

    return {
        level,
        stop: () =>
            new Promise<Blob>((resolve) => {
                recorder.onstop = () => {
                    release();
                    resolve(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
                };
                recorder.stop();
            }),
        cancel: () => {
            recorder.onstop = release;
            if (recorder.state !== "inactive") {
                recorder.stop();
            } else {
                release();
            }
        },
    };
}

/** A short soft tone: the word was heard, speak now. */
export async function chime(): Promise<void> {
    if (typeof AudioContext === "undefined") {
        return;
    }
    const context = new AudioContext();
    try {
        const tone = context.createOscillator();
        const gain = context.createGain();
        tone.frequency.value = 880;
        gain.gain.setValueAtTime(0.0001, context.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.15, context.currentTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.16);
        tone.connect(gain);
        gain.connect(context.destination);
        await new Promise<void>((resolve) => {
            tone.onended = () => resolve();
            // A suspended context never ends the tone: do not wait for it.
            setTimeout(resolve, 300);
            tone.start();
            tone.stop(context.currentTime + 0.18);
        });
    } catch {
        // No tone: the indicator still says it is listening.
    } finally {
        void context.close();
    }
}

function decodeBase64(data: string): ArrayBuffer {
    const binary = atob(data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
}

/**
 * Play a spoken reply (base64 audio from the backend). `onLevel` receives
 * the meter while it plays and a silent one when it ends.
 */
export async function playReply(
    audioBase64: string,
    onLevel: (level: () => number) => void,
): Promise<void> {
    const context = new AudioContext();
    try {
        const buffer = await context.decodeAudioData(decodeBase64(audioBase64));
        const source = context.createBufferSource();
        const analyser = context.createAnalyser();
        analyser.fftSize = 1024;
        source.buffer = buffer;
        source.connect(analyser);
        analyser.connect(context.destination);

        onLevel(levelMeter(analyser));
        await new Promise<void>((resolve) => {
            source.onended = () => resolve();
            source.start();
        });
    } finally {
        onLevel(silence);
        void context.close();
    }
}
