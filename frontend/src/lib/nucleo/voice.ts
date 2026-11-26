/**
 * @file frontend/src/lib/nucleo/voice.ts
 * @description Voice settings for the Control Plane and the Nucleo (F3,
 * ADR-021, ADR-024, ADR-038): what GET /api/voice says, what the choices mean, and
 * the changes the Voice page saves through PUT /api/settings.
 */

import type { SettingChanges, SettingField } from "@/lib/api/settings";
import { catalog, type Lang } from "@/lib/i18n";

export interface DownloadedModel {
    name: string;
    bytes: number;
}

export interface VoiceStatus {
    enabled: boolean;
    missing: string[];
    stt: { model: string; language: string };
    tts: {
        engine: "piper" | "elevenlabs" | "spacexai";
        piper_voice: string;
        elevenlabs_voice: string;
        elevenlabs_key: boolean;
        spacexai_key?: boolean;
        spacexai_usd_per_million_chars?: number;
        max_cloud_chars: number;
    };
    downloaded: { whisper: DownloadedModel[]; piper: DownloadedModel[] };
    /** The wake word (N2, ADR-041). */
    wake?: {
        word: string;
        label: string;
        threshold: number;
        own_model_path: string;
        downloaded: Record<string, boolean>;
    };
}

/** The wake words: three ready-made, and your own "aurora" model. */
export const WAKE_WORDS = ["off", "hey_jarvis", "alexa", "hey_mycroft", "aurora"] as const;
export const WAKE_SENSITIVITIES = ["low", "medium", "high"] as const;

export interface CloudVoice {
    id: string;
    name: string;
    labels: string;
}

/** The voice settings, in the order the page shows them. */
export const VOICE_SETTINGS = [
    // On or off, and when the models leave memory (F9).
    "AEHUB_VOICE",
    "AEHUB_VOICE_IDLE_MINUTES",
    "AEHUB_STT_MODEL",
    "AEHUB_STT_LANGUAGE",
    "AEHUB_TTS_ENGINE",
    "AEHUB_TTS_VOICE",
    "AEHUB_ELEVENLABS_VOICE",
    "AEHUB_ELEVENLABS_MODEL",
    "AEHUB_SPACEXAI_VOICE",
    "AEHUB_SPACEXAI_LANGUAGE",
    // The wake word (N2).
    "AEHUB_WAKE_WORD",
    "AEHUB_WAKE_SENSITIVITY",
] as const;

export type VoiceSetting = (typeof VOICE_SETTINGS)[number];
export type VoiceForm = Record<VoiceSetting, string>;

const STT_SIZES: Record<string, { download: string; ram: string }> = {
    tiny: { download: "75 MB", ram: "0.1 GB" },
    base: { download: "145 MB", ram: "0.2 GB" },
    small: { download: "480 MB", ram: "0.4 GB" },
    medium: { download: "1.5 GB", ram: "0.9 GB" },
    "large-v3-turbo": { download: "1.6 GB", ram: "1 GB" },
    "large-v3": { download: "3.1 GB", ram: "1.8 GB" },
};

const STT_LABELS = catalog<Record<string, string>>({
    en: {
        tiny: "fastest, least accurate",
        base: "fast, good for commands",
        small: "more accurate, still quick",
        medium: "accurate, slow on CPU",
        "large-v3-turbo": "very accurate, slower",
        "large-v3": "the most accurate, the slowest",
    },
    it: {
        tiny: "velocissimo, meno preciso",
        base: "veloce, buono per i comandi",
        small: "più preciso, ancora rapido",
        medium: "preciso, lento su CPU",
        "large-v3-turbo": "molto preciso, più lento",
        "large-v3": "il più preciso, il più lento",
    },
});

/**
 * faster-whisper models, int8 on CPU. Sizes are the download; RAM is a
 * rough figure while transcribing, to choose with eyes open.
 */
export function sttModels(lang: Lang): Record<string, { label: string; download: string; ram: string }> {
    const sized = (value: string) => (lang === "it" ? value.replace(".", ",") : value);
    return Object.fromEntries(
        Object.entries(STT_SIZES).map(([name, size]) => [
            name,
            { label: STT_LABELS[lang][name], download: sized(size.download), ram: `≈ ${sized(size.ram)}` },
        ]),
    );
}

/** The spoken languages speech recognition can expect. */
export const LANGUAGES = catalog<Record<string, string>>({
    en: {
        it: "Italian",
        en: "English",
        es: "Spanish",
        fr: "French",
        de: "German",
        pt: "Portuguese",
        auto: "Detect it",
    },
    it: {
        it: "Italiano",
        en: "Inglese",
        es: "Spagnolo",
        fr: "Francese",
        de: "Tedesco",
        pt: "Portoghese",
        auto: "Riconosci da sola",
    },
});

/** Suggestions only: any voice of the Piper catalogue can be typed. */
export const PIPER_VOICES = [
    "it_IT-paola-medium",
    "it_IT-riccardo-x_low",
    "en_US-lessac-medium",
    "en_GB-alba-medium",
    "es_ES-davefx-medium",
    "fr_FR-siwis-medium",
    "de_DE-thorsten-medium",
    "pt_BR-faber-medium",
];

export const ELEVENLABS_MODELS = catalog<Record<string, string>>({
    en: {
        eleven_flash_v2_5: "Flash v2.5: the fastest and cheapest",
        eleven_multilingual_v2: "Multilingual v2: more expressive",
        eleven_v3: "v3: the most expressive, slower",
    },
    it: {
        eleven_flash_v2_5: "Flash v2.5: il più rapido ed economico",
        eleven_multilingual_v2: "Multilingual v2: più espressivo",
        eleven_v3: "v3: il più espressivo, più lento",
    },
});

/** The two SpaceXAI voices ÆHub offers (ADR-038). */
export const SPACEXAI_VOICES = catalog<Record<string, string>>({
    en: {
        eve: "eve · energetic and cheerful, British accent (default)",
        altair: "altair · formal, elegant, premium",
    },
    it: {
        eve: "eve · energica e allegra, accento britannico (predefinita)",
        altair: "altair · formale, elegante, premium",
    },
});

/** The languages a SpaceXAI voice reads in: always a code, never "auto". */
export const SPACEXAI_LANGUAGES = ["it", "en", "fr"] as const;

/** What a month of replies costs with SpaceXAI, in dollars: replies a day × characters × 30 days. */
export function spacexaiMonthlyCost(repliesPerDay: number, charsPerReply: number, usdPerMillion = 15): number {
    return (repliesPerDay * charsPerReply * 30 * usdPerMillion) / 1_000_000;
}

/** The language a Piper voice speaks, from its name: it_IT-paola-medium → it. */
export function piperLanguage(voice: string): string | null {
    const code = voice.trim().split("_", 1)[0].toLowerCase();
    return /^[a-z]{2,3}$/.test(code) ? code : null;
}

const PREVIEW_TEXTS: Record<string, string> = {
    it: "Ciao, sono ÆHub. Questa è la mia voce.",
    en: "Hi, I am ÆHub. This is my voice.",
    es: "Hola, soy ÆHub. Esta es mi voz.",
    fr: "Bonjour, je suis ÆHub. Voici ma voix.",
    de: "Hallo, ich bin ÆHub. Das ist meine Stimme.",
    pt: "Olá, sou o ÆHub. Esta é a minha voz.",
};

/** The sample sentence of a voice, in the language the voice speaks (ADR-034). */
export function previewText(voiceLanguage: string | null, lang: Lang): string {
    return PREVIEW_TEXTS[voiceLanguage ?? ""] ?? PREVIEW_TEXTS[lang];
}

/** The current values of the voice settings, as the form starts. */
export function voiceForm(settings: SettingField[]): VoiceForm {
    const values = Object.fromEntries(settings.map((field) => [field.name, field.value]));
    return Object.fromEntries(VOICE_SETTINGS.map((name) => [name, values[name] ?? ""])) as VoiceForm;
}

/** Only what changed; an emptied field goes back to the default (null). */
export function voiceChanges(saved: VoiceForm, form: VoiceForm): SettingChanges {
    const changes: SettingChanges = {};
    for (const name of VOICE_SETTINGS) {
        const value = form[name].trim();
        if (value !== saved[name]) {
            changes[name] = value === "" ? null : value;
        }
    }
    return changes;
}

/** "145 MB", "1.5 GB" (Italian: "1,5 GB"). */
export function formatBytes(bytes: number, lang: Lang = "en"): string {
    if (bytes >= 1024 ** 3) {
        const value = (bytes / 1024 ** 3).toFixed(1);
        return `${lang === "it" ? value.replace(".", ",") : value} GB`;
    }
    if (bytes >= 1024 ** 2) {
        return `${Math.round(bytes / 1024 ** 2)} MB`;
    }
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Whether `run.resumed` belongs to a run asked by voice (F3). */
export function resumedByVoice(data: Record<string, unknown>): boolean {
    return data.input_channel === "voice";
}

// ==============================================================================
// SENTENCE BY SENTENCE (N1, ADR-040)
// ==============================================================================

// A piece shorter than this joins the next one: fewer requests, natural pauses.
const MIN_PIECE = 40;
// A longer sentence is cut at a comma or a space, so the first sound comes soon.
const MAX_PIECE = 280;

function cut(sentence: string): string[] {
    const pieces: string[] = [];
    let rest = sentence.trim();
    while (rest.length > MAX_PIECE) {
        const window = rest.slice(0, MAX_PIECE);
        const at = Math.max(window.lastIndexOf(", "), window.lastIndexOf("; "));
        const split = at > MIN_PIECE ? at + 1 : window.lastIndexOf(" ") > MIN_PIECE ? window.lastIndexOf(" ") : MAX_PIECE;
        pieces.push(rest.slice(0, split).trim());
        rest = rest.slice(split).trim();
    }
    if (rest) {
        pieces.push(rest);
    }
    return pieces;
}

/** The reply in pieces to speak one after another: whole sentences, none too short or too long. */
export function splitSentences(text: string): string[] {
    const sentences = text
        .replace(/\s+/g, " ")
        .trim()
        .split(/(?<=[.!?…:;])\s+(?=\S)/)
        .flatMap(cut)
        .filter(Boolean);

    const pieces: string[] = [];
    for (const sentence of sentences) {
        const last = pieces[pieces.length - 1];
        if (last !== undefined && last.length < MIN_PIECE && last.length + sentence.length + 1 <= MAX_PIECE) {
            pieces[pieces.length - 1] = `${last} ${sentence}`;
        } else {
            pieces.push(sentence);
        }
    }
    return pieces;
}

export interface SpokenPiece {
    audio_base64: string;
    audio_mime: string;
}

/**
 * Speak the pieces in order: the next one is synthesized while the current
 * one plays. Stops when a piece has no audio (voice off) or `stillWanted`
 * says a newer reply took over.
 */
export async function speakInSentences(
    pieces: string[],
    synthesize: (piece: string) => Promise<SpokenPiece | null>,
    play: (audioBase64: string) => Promise<void>,
    stillWanted: () => boolean = () => true,
): Promise<number> {
    let spoken = 0;
    let next: Promise<SpokenPiece | null> | null = pieces.length ? synthesize(pieces[0]) : null;
    for (let index = 0; index < pieces.length && next; index++) {
        const current = await next.catch(() => null);
        next = index + 1 < pieces.length ? synthesize(pieces[index + 1]) : null;
        if (!current?.audio_base64 || !stillWanted()) {
            next?.catch(() => null);
            break;
        }
        await play(current.audio_base64);
        spoken += 1;
    }
    return spoken;
}

