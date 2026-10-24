/**
 * @file frontend/src/lib/nucleo/audio.ts
 * @description Audio for the Nucleo: the microphone with its live level,
 * and the spoken reply played through a level meter so the sphere moves
 * with the real voice.
 */

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

/** Open the microphone and start recording. Rejects when it is refused. */
export async function startRecording(): Promise<Recording> {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        throw new Error("Il microfono non è disponibile in questo browser.");
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

    const release = () => {
        stream.getTracks().forEach((track) => track.stop());
        void context.close();
    };

    return {
        level: levelMeter(analyser),
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
