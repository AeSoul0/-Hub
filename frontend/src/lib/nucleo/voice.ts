/**
 * @file frontend/src/lib/nucleo/voice.ts
 * @description Voice settings for the Control Plane and the Nucleo (F3,
 * ADR-021, ADR-024): what GET /api/voice says, what the choices mean, and
 * the changes the Voice page saves through PUT /api/settings.
 */

import type { SettingChanges, SettingField } from "@/lib/api/settings";

export interface DownloadedModel {
    name: string;
    bytes: number;
}

export interface VoiceStatus {
    enabled: boolean;
    missing: string[];
    stt: { model: string; language: string };
    tts: {
        engine: "piper" | "elevenlabs";
        piper_voice: string;
        elevenlabs_voice: string;
        elevenlabs_key: boolean;
        max_cloud_chars: number;
    };
    downloaded: { whisper: DownloadedModel[]; piper: DownloadedModel[] };
}

export interface CloudVoice {
    id: string;
    name: string;
    labels: string;
}

/** The voice settings, in the order the page shows them. */
export const VOICE_SETTINGS = [
    "AEHUB_STT_MODEL",
    "AEHUB_STT_LANGUAGE",
    "AEHUB_TTS_ENGINE",
    "AEHUB_TTS_VOICE",
    "AEHUB_ELEVENLABS_VOICE",
    "AEHUB_ELEVENLABS_MODEL",
] as const;

export type VoiceSetting = (typeof VOICE_SETTINGS)[number];
export type VoiceForm = Record<VoiceSetting, string>;

/**
 * faster-whisper models, int8 on CPU. Sizes are the download; RAM is a
 * rough figure while transcribing, to choose with eyes open.
 */
export const STT_MODELS: Record<string, { label: string; download: string; ram: string }> = {
    tiny: { label: "velocissimo, meno preciso", download: "75 MB", ram: "≈ 0,1 GB" },
    base: { label: "veloce, buono per i comandi", download: "145 MB", ram: "≈ 0,2 GB" },
    small: { label: "più preciso, ancora rapido", download: "480 MB", ram: "≈ 0,4 GB" },
    medium: { label: "preciso, lento su CPU", download: "1,5 GB", ram: "≈ 0,9 GB" },
    "large-v3-turbo": { label: "molto preciso, più lento", download: "1,6 GB", ram: "≈ 1 GB" },
    "large-v3": { label: "il più preciso, il più lento", download: "3,1 GB", ram: "≈ 1,8 GB" },
};

export const LANGUAGES: Record<string, string> = {
    it: "Italiano",
    en: "Inglese",
    es: "Spagnolo",
    fr: "Francese",
    de: "Tedesco",
    pt: "Portoghese",
    auto: "Riconosci da sola",
};

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

export const ELEVENLABS_MODELS: Record<string, string> = {
    eleven_flash_v2_5: "Flash v2.5: il più rapido ed economico",
    eleven_multilingual_v2: "Multilingual v2: più espressivo",
    eleven_v3: "v3: il più espressivo, più lento",
};

export const PREVIEW_TEXT = "Ciao, sono ÆHub. Questa è la mia voce.";

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

/** "145 MB", "1,5 GB". */
export function formatBytes(bytes: number): string {
    if (bytes >= 1024 ** 3) {
        return `${(bytes / 1024 ** 3).toFixed(1).replace(".", ",")} GB`;
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
