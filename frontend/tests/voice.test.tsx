/**
 * @file frontend/tests/voice.test.tsx
 * @description Tests of Voce: the voice helpers and VoicePage.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import React from "react";
import { beforeEach, describe, expect, it } from "vitest";

import VoicePage from "@/app/control-plane/voice/page";
import type { SettingField, SettingsView } from "@/lib/api/settings";
import {
    formatBytes,
    resumedByVoice,
    spacexaiMonthlyCost,
    voiceChanges,
    voiceForm,
    type VoiceStatus,
} from "@/lib/nucleo/voice";

import { stubFetch } from "./helpers";

import { chooseLanguage } from "@/lib/i18n";

// These tests read the Italian interface; interface.test.tsx covers the English default.
beforeEach(() => chooseLanguage("it"));

const VOICE_ID = "Xb7hH8MSUJpSbSDYk0k2";

function voiceField(name: string, value: string, options: string[] = []): SettingField {
    return {
        name,
        group: "voice",
        label: name,
        kind: options.length ? "choice" : "text",
        help: "",
        default: value,
        value,
        source: "default",
        options,
    };
}

function settingsView(values: Record<string, string> = {}, issues: SettingsView["issues"] = []): SettingsView {
    const value = (name: string, fallback: string) => values[name] ?? fallback;
    return {
        settings: [
            voiceField("AEHUB_STT_MODEL", value("AEHUB_STT_MODEL", "base"), ["tiny", "base", "small"]),
            voiceField("AEHUB_STT_LANGUAGE", value("AEHUB_STT_LANGUAGE", "it"), ["it", "en", "auto"]),
            voiceField("AEHUB_TTS_ENGINE", value("AEHUB_TTS_ENGINE", "piper"), ["piper", "elevenlabs", "spacexai"]),
            voiceField("AEHUB_TTS_VOICE", value("AEHUB_TTS_VOICE", "it_IT-paola-medium")),
            voiceField("AEHUB_ELEVENLABS_VOICE", value("AEHUB_ELEVENLABS_VOICE", "")),
            voiceField("AEHUB_ELEVENLABS_MODEL", value("AEHUB_ELEVENLABS_MODEL", "eleven_flash_v2_5")),
            voiceField("AEHUB_SPACEXAI_VOICE", value("AEHUB_SPACEXAI_VOICE", "eve"), ["eve", "altair"]),
            voiceField("AEHUB_SPACEXAI_LANGUAGE", value("AEHUB_SPACEXAI_LANGUAGE", "it"), ["it", "en", "fr"]),
            voiceField("AEHUB_WAKE_WORD", value("AEHUB_WAKE_WORD", "off"), ["off", "hey_jarvis", "alexa", "hey_mycroft", "aurora"]),
            voiceField("AEHUB_WAKE_SENSITIVITY", value("AEHUB_WAKE_SENSITIVITY", "medium"), ["low", "medium", "high"]),
        ],
        secrets: [],
        issues,
        models: [],
        roles: {
            architect: { chain: ["openai:gpt-5.5"], custom: false },
            research: { chain: ["openai:gpt-5.5"], custom: false },
            critic: { chain: ["openai:critic"], custom: false },
            fast_worker: { chain: ["openai:gpt-5.5"], custom: false },
            triage: { chain: ["openai:gpt-5.5"], custom: false },
        },
        providers: {
            openai: { key: true, needs_key: true },
            openrouter: { key: false, needs_key: true },
            local: { key: false, needs_key: false },
        },
        workspace: { path: "/w", exists: true },
        ready: true,
        onboarding: { completed: true, completed_at: "2026-10-26T10:00:00Z" },
    };
}

function status(overrides: Partial<VoiceStatus["tts"]> = {}): VoiceStatus {
    return {
        enabled: true,
        missing: [],
        stt: { model: "base", language: "it" },
        tts: {
            engine: "piper",
            piper_voice: "it_IT-paola-medium",
            elevenlabs_voice: "",
            elevenlabs_key: false,
            max_cloud_chars: 2500,
            ...overrides,
        },
        downloaded: {
            whisper: [{ name: "base", bytes: 145 * 1024 ** 2 }],
            piper: [{ name: "it_IT-paola-medium", bytes: 63 * 1024 ** 2 }],
        },
    };
}

describe("voice helpers", () => {
    it("keeps only the changes, an emptied field back to the default", () => {
        const saved = voiceForm(settingsView().settings);
        expect(saved.AEHUB_STT_MODEL).toBe("base");

        expect(voiceChanges(saved, { ...saved })).toEqual({});
        expect(voiceChanges(saved, { ...saved, AEHUB_STT_MODEL: "small", AEHUB_TTS_VOICE: " " })).toEqual({
            AEHUB_STT_MODEL: "small",
            AEHUB_TTS_VOICE: null,
        });
    });

    it("estimates what SpaceXAI costs a month", () => {
        // 15 $ per million characters, replies of about 500 characters.
        expect(spacexaiMonthlyCost(10, 500)).toBeCloseTo(2.25);
        expect(spacexaiMonthlyCost(100, 500)).toBeCloseTo(22.5);
    });

    it("formats sizes and recognises a voice run", () => {
        expect(formatBytes(145 * 1024 ** 2, "it")).toBe("145 MB");
        expect(formatBytes(1.5 * 1024 ** 3, "it")).toBe("1,5 GB");
        expect(formatBytes(10, "it")).toBe("1 KB");
        expect(resumedByVoice({ input_channel: "voice" })).toBe(true);
        expect(resumedByVoice({ input_channel: "text" })).toBe(false);
        expect(resumedByVoice({})).toBe(false);
    });
});

describe("VoicePage", () => {
    it("saves the recognition model and shows the models on disk", async () => {
        let current = settingsView();
        const fetch = stubFetch({
            "GET /api/settings": () => ({ status: 200, body: current }),
            "PUT /api/settings": () => {
                current = settingsView({ AEHUB_STT_MODEL: "small" });
                return { status: 200, body: current };
            },
            "GET /api/voice": () => ({ status: 200, body: status() }),
            "GET /api/desktop": () => ({ status: 200, body: { desktop: false } }),
        });

        render(<VoicePage />);

        const model = await screen.findByRole("combobox", { name: "Modello" });
        expect(screen.getByText("attiva")).toBeInTheDocument();
        expect(screen.getByText("riconoscimento · base")).toBeInTheDocument();
        expect(screen.getByText("145 MB")).toBeInTheDocument();

        const save = screen.getByRole("button", { name: "Salva" });
        expect(save).toBeDisabled();

        fireEvent.change(model, { target: { value: "small" } });
        expect(screen.getByText(/Download 480 MB/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Ascolta" })).toBeDisabled();

        fireEvent.click(save);
        expect(await screen.findByText("Salvato: vale dalla prossima frase.")).toBeInTheDocument();

        const put = fetch.mock.calls.find(([, init]) => init?.method === "PUT");
        expect(JSON.parse(String(put?.[1]?.body))).toEqual({ values: { AEHUB_STT_MODEL: "small" } });
    });

    it("chooses an ElevenLabs voice and shows why the preview fails", async () => {
        let current = settingsView({}, [
            {
                code: "voice_cloud_voice_missing",
                severity: "warning",
                message: "The ElevenLabs voice is chosen but no voice is selected.",
                setting: "AEHUB_ELEVENLABS_VOICE",
            },
        ]);
        const fetch = stubFetch({
            "GET /api/settings": () => ({ status: 200, body: current }),
            "PUT /api/settings": () => {
                current = settingsView({ AEHUB_TTS_ENGINE: "elevenlabs", AEHUB_ELEVENLABS_VOICE: VOICE_ID });
                return { status: 200, body: current };
            },
            "GET /api/voice": () => ({ status: 200, body: status({ elevenlabs_key: true }) }),
            "GET /api/desktop": () => ({ status: 200, body: { desktop: true } }),
            "GET /api/voice/elevenlabs/voices": () => ({
                status: 200,
                body: { voices: [{ id: VOICE_ID, name: "Bianca", labels: "female, italian" }] },
            }),
            "POST /api/voice/speak": () => ({ status: 503, body: { detail: "ElevenLabs answered 401: Invalid API key" } }),
        });

        render(<VoicePage />);

        expect(await screen.findByText(/no voice is selected/)).toBeInTheDocument();
        fireEvent.click(screen.getByRole("radio", { name: /ElevenLabs/ }));
        expect(screen.getByText(/il testo delle risposte va ai suoi server/)).toBeInTheDocument();
        expect(screen.getByText("chiave impostata")).toBeInTheDocument();
        expect(screen.getByLabelText("Chiave API ElevenLabs")).toHaveAttribute("type", "password");

        fireEvent.click(screen.getByRole("button", { name: "Carica le voci" }));
        const voices = await screen.findByRole("combobox", { name: "Voce ElevenLabs" });
        fireEvent.change(voices, { target: { value: VOICE_ID } });
        expect(within(voices).getByRole("option", { name: "Bianca · female, italian" })).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Salva" }));
        await screen.findByText("Salvato: vale dalla prossima frase.");
        const put = fetch.mock.calls.find(([, init]) => init?.method === "PUT");
        expect(JSON.parse(String(put?.[1]?.body))).toEqual({
            values: { AEHUB_TTS_ENGINE: "elevenlabs", AEHUB_ELEVENLABS_VOICE: VOICE_ID },
        });

        const listen = screen.getByRole("button", { name: "Ascolta" });
        await waitFor(() => expect(listen).toBeEnabled());
        fireEvent.click(listen);
        expect(await screen.findByRole("alert")).toHaveTextContent("401: Invalid API key");

        const speak = fetch.mock.calls.find(([url]) => String(url).endsWith("/api/voice/speak"));
        expect(JSON.parse(String(speak?.[1]?.body))).toEqual({ text: "Ciao, sono ÆHub. Questa è la mia voce.", preview: true });
    });

    it("chooses SpaceXAI with its voice, an explicit language and the key", async () => {
        let current = settingsView();
        const fetch = stubFetch({
            "GET /api/settings": () => ({ status: 200, body: current }),
            "PUT /api/settings": () => {
                current = settingsView({
                    AEHUB_TTS_ENGINE: "spacexai",
                    AEHUB_SPACEXAI_VOICE: "altair",
                    AEHUB_SPACEXAI_LANGUAGE: "fr",
                });
                return { status: 200, body: current };
            },
            "GET /api/voice": () => ({
                status: 200,
                body: status({ spacexai_key: false, spacexai_usd_per_million_chars: 15 }),
            }),
            "GET /api/desktop": () => ({ status: 200, body: { desktop: true } }),
            "PUT /api/desktop/secrets": () => ({ status: 200, body: { saved: ["XAI_API_KEY"] } }),
            "POST /api/voice/speak": () => ({ status: 200, body: { audio_base64: "", audio_mime: "" } }),
        });

        render(<VoicePage />);

        fireEvent.click(await screen.findByRole("radio", { name: /SpaceXAI/ }));
        expect(screen.getByText(/va ai server di xAI/)).toBeInTheDocument();
        expect(screen.getByText("chiave mancante")).toBeInTheDocument();
        expect(screen.getByText(/15,00 \$ per milione di caratteri/)).toBeInTheDocument();
        expect(screen.getByText(/circa 2,25 \$ al mese con 10 al giorno, 22,50 \$ con 100 al giorno/)).toBeInTheDocument();

        const voice = screen.getByRole("combobox", { name: "Voce SpaceXAI" });
        expect(within(voice).getAllByRole("option").map((option) => option.getAttribute("value"))).toEqual(["eve", "altair"]);
        fireEvent.change(voice, { target: { value: "altair" } });
        const language = screen.getByRole("combobox", { name: "Lingua in cui legge" });
        expect(within(language).getAllByRole("option").map((option) => option.getAttribute("value"))).toEqual(["it", "en", "fr"]);
        fireEvent.change(language, { target: { value: "fr" } });
        expect(screen.getByText("Questa voce parla francese: le risposte vengono lette in francese.")).toBeInTheDocument();

        fireEvent.change(screen.getByLabelText("Chiave API SpaceXAI (xAI)"), { target: { value: "xai-test-key" } });
        fireEvent.click(screen.getByRole("button", { name: "Salva la chiave" }));
        await screen.findByText("Chiave salvata nel portachiavi del sistema.");
        const secret = fetch.mock.calls.find(([url]) => String(url).endsWith("/api/desktop/secrets"));
        expect(JSON.parse(String(secret?.[1]?.body))).toEqual({ XAI_API_KEY: "xai-test-key" });

        fireEvent.click(screen.getByRole("button", { name: "Salva" }));
        await screen.findByText("Salvato: vale dalla prossima frase.");
        const put = fetch.mock.calls.find(([, init]) => init?.method === "PUT" && String(init?.body).includes("values"));
        expect(JSON.parse(String(put?.[1]?.body))).toEqual({
            values: { AEHUB_TTS_ENGINE: "spacexai", AEHUB_SPACEXAI_VOICE: "altair", AEHUB_SPACEXAI_LANGUAGE: "fr" },
        });

        const listen = screen.getByRole("button", { name: "Ascolta" });
        await waitFor(() => expect(listen).toBeEnabled());
        fireEvent.click(listen);
        await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/api/voice/speak"))).toBe(true));
        const speak = fetch.mock.calls.find(([url]) => String(url).endsWith("/api/voice/speak"));
        expect(JSON.parse(String(speak?.[1]?.body))).toEqual({ text: "Bonjour, je suis ÆHub. Voici ma voix.", preview: true });
    });

    it("chooses a wake word and its sensitivity; aurora says where its model goes", async () => {
        let current = settingsView();
        const fetch = stubFetch({
            "GET /api/settings": () => ({ status: 200, body: current }),
            "PUT /api/settings": () => {
                current = settingsView({ AEHUB_WAKE_WORD: "aurora", AEHUB_WAKE_SENSITIVITY: "high" });
                return { status: 200, body: current };
            },
            "GET /api/voice": () => ({
                status: 200,
                body: {
                    ...status(),
                    wake: {
                        word: "off",
                        label: "",
                        threshold: 0.5,
                        own_model_path: "/home/me/.cache/aehub/voice/wake/aurora.onnx",
                        downloaded: { aurora: false },
                    },
                },
            }),
            "GET /api/desktop": () => ({ status: 200, body: { desktop: false } }),
        });

        render(<VoicePage />);

        const word = await screen.findByRole("combobox", { name: "Parola" });
        expect(within(word).getAllByRole("option").map((option) => option.textContent)).toEqual([
            "spenta · premi il microfono",
            "Hey Jarvis",
            "Alexa",
            "Hey Mycroft",
            "Aurora · il tuo modello",
        ]);
        const sensitivity = screen.getByRole("combobox", { name: "Sensibilità" });
        // Nothing to tune while the word is off.
        expect(sensitivity).toBeDisabled();
        expect(screen.getByText(/nessun audio viene registrato né inviato/)).toBeInTheDocument();

        fireEvent.change(word, { target: { value: "aurora" } });
        expect(
            screen.getByText(/Aurora richiede un tuo modello openWakeWord .* in \/home\/me\/.cache\/aehub\/voice\/wake\/aurora.onnx\. Il file non c'è ancora\./)
        ).toBeInTheDocument();
        fireEvent.change(sensitivity, { target: { value: "high" } });

        fireEvent.click(screen.getByRole("button", { name: "Salva" }));
        await screen.findByText("Salvato: vale dalla prossima frase.");
        const put = fetch.mock.calls.find(([, init]) => init?.method === "PUT");
        expect(JSON.parse(String(put?.[1]?.body))).toEqual({
            values: { AEHUB_WAKE_WORD: "aurora", AEHUB_WAKE_SENSITIVITY: "high" },
        });
    });
});
