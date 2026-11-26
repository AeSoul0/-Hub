/**
 * @file frontend/src/lib/nucleo/wake.ts
 * @description The wake word (N2, ADR-041), the part without the browser:
 * openWakeWord's streaming pipeline, the resampling of the microphone to
 * 16 kHz, the trigger with its pause, and the end of a spoken command.
 *
 * openWakeWord turns audio into a score in three models, every 80 ms (1280
 * samples at 16 kHz):
 * 1. melspectrogram: the new samples, with the 480 before them, become 8
 *    frames of 32 values (transformed as x / 10 + 2);
 * 2. embedding: the last 76 frames become one vector of 96;
 * 3. the word: the last 16 vectors (1.28 s) become a score from 0 to 1.
 * The models run in the browser (wakeListener.ts); here they are functions,
 * so the pipeline can be tested without them.
 */

export const SAMPLE_RATE = 16000;
export const CHUNK = 1280;
const MEL_CONTEXT = 480;
export const MEL_BINS = 32;
export const MEL_WINDOW = 76;
export const EMBEDDING = 96;
export const FEATURES = 16;
// openWakeWord keeps 10 s of frames; the pipeline only ever needs the last 76.
const MEL_KEEP = MEL_WINDOW;
// The first scores of a fresh pipeline are not reliable (openWakeWord zeroes 5).
const WARMUP_SCORES = 5;

export interface WakeModels {
    /** int16-scaled samples -> frames x 32 mel values (raw, not transformed). */
    mel(samples: Float32Array): Promise<Float32Array>;
    /** 76 x 32 transformed frames -> 96 values. */
    embed(window: Float32Array): Promise<Float32Array>;
    /** 16 x 96 features -> the score of the word, 0..1. */
    score(features: Float32Array): Promise<number>;
}

export class WakePipeline {
    private pending: number[] = [];
    private context = new Float32Array(0);
    private mel: Float32Array[] = [];
    private features: Float32Array[] = [];
    private scored = 0;

    constructor(private readonly models: WakeModels) {
        this.reset();
    }

    /** Start again from silence, as after a pause: old audio cannot trigger. */
    reset(): void {
        this.pending = [];
        this.context = new Float32Array(0);
        // Like openWakeWord: the frame buffer starts as ones.
        this.mel = Array.from({ length: MEL_WINDOW }, () => new Float32Array(MEL_BINS).fill(1));
        this.features = [];
        this.scored = 0;
    }

    /** More samples at 16 kHz, int16-scaled; one score per full chunk. */
    async push(samples: Float32Array): Promise<number[]> {
        for (let i = 0; i < samples.length; i++) {
            this.pending.push(samples[i]);
        }
        const scores: number[] = [];
        while (this.pending.length >= CHUNK) {
            const chunk = Float32Array.from(this.pending.splice(0, CHUNK));
            scores.push(await this.step(chunk));
        }
        return scores;
    }

    private async step(chunk: Float32Array): Promise<number> {
        const input = new Float32Array(this.context.length + chunk.length);
        input.set(this.context);
        input.set(chunk, this.context.length);
        this.context = input.slice(Math.max(0, input.length - MEL_CONTEXT));

        const raw = await this.models.mel(input);
        for (let offset = 0; offset + MEL_BINS <= raw.length; offset += MEL_BINS) {
            const frame = new Float32Array(MEL_BINS);
            for (let bin = 0; bin < MEL_BINS; bin++) {
                frame[bin] = raw[offset + bin] / 10 + 2;
            }
            this.mel.push(frame);
        }
        this.mel.splice(0, Math.max(0, this.mel.length - MEL_KEEP));

        const window = new Float32Array(MEL_WINDOW * MEL_BINS);
        this.mel.forEach((frame, index) => window.set(frame, index * MEL_BINS));
        this.features.push(await this.models.embed(window));
        this.features.splice(0, Math.max(0, this.features.length - FEATURES));

        if (this.features.length < FEATURES) {
            return 0;
        }
        const features = new Float32Array(FEATURES * EMBEDDING);
        this.features.forEach((feature, index) => features.set(feature, index * EMBEDDING));
        const score = await this.models.score(features);
        this.scored += 1;
        return this.scored <= WARMUP_SCORES ? 0 : score;
    }
}

/**
 * The microphone at its own rate (usually 48 kHz) to 16 kHz, block by block:
 * a moving average as low-pass, then linear interpolation. The output is
 * int16-scaled, as openWakeWord expects.
 */
export class Resampler {
    private readonly step: number;
    private readonly width: number;
    private history: number[] = [];
    private sum = 0;
    private previous = 0;
    private position = 0;

    constructor(fromRate: number, toRate = SAMPLE_RATE) {
        this.step = fromRate / toRate;
        this.width = Math.max(1, Math.round(this.step));
    }

    process(input: Float32Array): Float32Array {
        const out: number[] = [];
        for (let i = 0; i < input.length; i++) {
            this.history.push(input[i]);
            this.sum += input[i];
            if (this.history.length > this.width) {
                this.sum -= this.history.shift() as number;
            }
            const current = this.sum / this.history.length;
            // Output samples fall between the previous filtered sample (at -1) and this one (at 0).
            while (this.position <= 0) {
                const fraction = this.position + 1;
                const value = this.previous + (current - this.previous) * fraction;
                out.push(Math.max(-32768, Math.min(32767, Math.round(value * 32767))));
                this.position += this.step;
            }
            this.position -= 1;
            this.previous = current;
        }
        return Float32Array.from(out);
    }
}

/** The word was heard: once over the threshold, then quiet for a while. */
export class WakeTrigger {
    private quietUntil = 0;

    constructor(
        private readonly threshold: number,
        private readonly cooldownMs = 2000
    ) {}

    hit(score: number, now: number): boolean {
        if (now < this.quietUntil || score < this.threshold) {
            return false;
        }
        this.quietUntil = now + this.cooldownMs;
        return true;
    }
}

export interface CommandEnd {
    /** Silence after speech that ends the command. */
    silenceMs: number;
    /** Nothing said at all for this long: stop anyway. */
    noSpeechMs: number;
    /** The longest command. */
    maxMs: number;
    /** Level (0..1, as the microphone meter) that counts as speech. */
    speechLevel: number;
}

export const COMMAND_END: CommandEnd = {
    silenceMs: 1200,
    noSpeechMs: 6000,
    maxMs: 20000,
    speechLevel: 0.12,
};

/**
 * Whether a command spoken after the word is over, from the microphone
 * level over time. Call `update(level, now)` every ~100 ms.
 */
export class CommandEndWatch {
    private heard = false;
    private lastLoud: number;
    private readonly started: number;

    constructor(
        now: number,
        private readonly rules: CommandEnd = COMMAND_END
    ) {
        this.started = now;
        this.lastLoud = now;
    }

    update(level: number, now: number): boolean {
        if (level >= this.rules.speechLevel) {
            this.heard = true;
            this.lastLoud = now;
        }
        if (now - this.started >= this.rules.maxMs) {
            return true;
        }
        return this.heard
            ? now - this.lastLoud >= this.rules.silenceMs
            : now - this.started >= this.rules.noSpeechMs;
    }
}
