/**
 * @file frontend/src/app/control-plane/voice/page.tsx
 * @description Voice (F3, ADR-021, ADR-024): speech recognition model and
 * language, the voice of the replies (Piper on this computer or, optional,
 * ElevenLabs or SpaceXAI, ADR-038) and the language it speaks, a preview in that language
 * (ADR-034), and the speech models already on disk.
 *
 * Reads GET /api/voice and the "voice" group of GET /api/settings; saves
 * through PUT /api/settings (applied to the next sentence, no restart). The
 * ElevenLabs and SpaceXAI keys go to the OS keyring (PUT /api/desktop/secrets) and is
 * never shown again. The preview is POST /api/voice/speak with preview=true.
 */
"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

import { useDesktopMode } from "@/components/control-plane/DesktopKeys";
import styles from "@/components/control-plane/control.module.css";
import { ApiError, getJson, postJson, putJson } from "@/lib/api/client";
import { useSettings } from "@/lib/api/settings";
import { playReply } from "@/lib/nucleo/audio";
import { LANGUAGE_NAMES, catalog, useLanguage, useText } from "@/lib/i18n";
import { issueText } from "@/lib/nucleo/models";
import {
    ELEVENLABS_MODELS,
    formatBytes,
    LANGUAGES,
    PIPER_VOICES,
    piperLanguage,
    previewText as sampleSentence,
    SPACEXAI_LANGUAGES,
    SPACEXAI_VOICES,
    spacexaiMonthlyCost,
    sttModels,
    voiceChanges,
    voiceForm,
    type CloudVoice,
    type VoiceForm,
    type VoiceStatus,
} from "@/lib/nucleo/voice";

function message(err: unknown): string {
    return err instanceof Error ? err.message : String(err);
}

const TEXT = catalog({
    en: {
        off: "off",
        missing: (packages: string) => `missing ${packages}`,
        on: "on",
        saved: "Saved: it applies from the next sentence.",
        notSaved: "Not saved.",
        keySaved: "Key saved in the system keyring.",
        unavailable: "Settings not available:",
        loading: "Loading the voice…",
        title: "VOICE",
        form: "Voice settings",
        power: "On/off and memory",
        voice: "Voice",
        voiceOn: "on",
        voiceOff: "off",
        idle: "Release the models after (minutes)",
        idleHelp:
            "Whisper, Piper and the memory's embedding model leave memory after this long without use and load again when needed (1–2 seconds more, only that time). 0 keeps them always loaded.",
        recognition: "Speech recognition",
        model: "Model",
        language: "Language",
        sttInfo: (download: string, ram: string) =>
            `Downloads ${download} the first time, RAM ${ram} while transcribing. It runs on this computer: the audio never leaves.`,
        replyVoice: "Voice of the replies",
        engine: "Voice engine",
        piper: "Piper · on this computer",
        elevenlabs: "ElevenLabs · in the cloud",
        spacexai: "SpaceXAI · in the cloud",
        spacexaiWarning: (chars: number) =>
            `With SpaceXAI the text of the replies goes to xAI's servers to become voice; the microphone stays local. If the cloud does not answer, or the reply is longer than ${chars} characters, Piper speaks.`,
        spacexaiKey: "SpaceXAI (xAI) API key",
        spacexaiVoice: "SpaceXAI voice",
        spacexaiLanguage: "Language it reads in",
        spacexaiPrice: (perMillion: string, low: string, high: string) =>
            `Pay per use, no subscription: ${perMillion} $ per million characters. With replies of about 500 characters: about ${low} $ a month at 10 a day, ${high} $ at 100 a day. The model that writes the replies is paid apart.`,
        piperFallback: "Fallback Piper voice",
        piperVoice: "Piper voice",
        speaks: (language: string) => `This voice speaks ${language}: replies are read in ${language}.`,
        speaksUnknown: "The language of this voice cannot be read from its name.",
        cloudWarning: (chars: number) =>
            `With ElevenLabs the text of the replies goes to its servers to become voice; the microphone stays local. If the cloud does not answer, or the reply is longer than ${chars} characters, Piper speaks.`,
        keySet: "key set",
        keyMissing: "key missing",
        apiKey: "ElevenLabs API key",
        saveKey: "Save the key",
        addWith: "Add it with",
        cloudVoice: "ElevenLabs voice",
        chooseVoice: "Choose a voice",
        voiceId: "Voice ID",
        loadVoices: "Load the voices",
        save: "Save",
        cancel: "Cancel",
        preview: "Preview",
        sentence: "Sentence",
        speaking: "Speaking…",
        listen: "Listen",
        saveFirst: "Save to hear the new voice.",
        firstTime: "The first time the voice is downloaded: it can take a few seconds.",
        downloaded: "Downloaded models",
        recognitionModel: "recognition",
        piperModel: "Piper voice",
        none: "None yet: they are downloaded the first time you use the microphone and the voice.",
    },
    it: {
        off: "spenta",
        missing: (packages: string) => `mancano ${packages}`,
        on: "attiva",
        saved: "Salvato: vale dalla prossima frase.",
        notSaved: "Non salvato.",
        keySaved: "Chiave salvata nel portachiavi del sistema.",
        unavailable: "Impostazioni non disponibili:",
        loading: "Carico la voce…",
        title: "VOCE",
        form: "Impostazioni della voce",
        power: "Accensione e memoria",
        voice: "Voce",
        voiceOn: "accesa",
        voiceOff: "spenta",
        idle: "Libera i modelli dopo (minuti)",
        idleHelp:
            "Whisper, Piper e il modello della memoria escono dalla RAM dopo questo tempo senza usarli e si ricaricano quando servono (1–2 secondi in più solo quella volta). 0 li tiene sempre caricati.",
        recognition: "Riconoscimento vocale",
        model: "Modello",
        language: "Lingua",
        sttInfo: (download: string, ram: string) =>
            `Download ${download} la prima volta, RAM ${ram} mentre trascrive. Gira su questo computer: l'audio non esce mai.`,
        replyVoice: "Voce delle risposte",
        engine: "Motore della voce",
        piper: "Piper · su questo computer",
        elevenlabs: "ElevenLabs · nel cloud",
        spacexai: "SpaceXAI · nel cloud",
        spacexaiWarning: (chars: number) =>
            `Con SpaceXAI il testo delle risposte va ai server di xAI per diventare voce; il microfono resta locale. Se il cloud non risponde, o la risposta supera ${chars} caratteri, parla Piper.`,
        spacexaiKey: "Chiave API SpaceXAI (xAI)",
        spacexaiVoice: "Voce SpaceXAI",
        spacexaiLanguage: "Lingua in cui legge",
        spacexaiPrice: (perMillion: string, low: string, high: string) =>
            `A consumo, senza abbonamento: ${perMillion} $ per milione di caratteri. Con risposte da circa 500 caratteri: circa ${low} $ al mese con 10 al giorno, ${high} $ con 100 al giorno. Il modello che scrive le risposte si paga a parte.`,
        piperFallback: "Voce Piper di riserva",
        piperVoice: "Voce Piper",
        speaks: (language: string) => `Questa voce parla ${language}: le risposte vengono lette in ${language}.`,
        speaksUnknown: "La lingua di questa voce non si legge dal suo nome.",
        cloudWarning: (chars: number) =>
            `Con ElevenLabs il testo delle risposte va ai suoi server per diventare voce; il microfono resta locale. Se il cloud non risponde, o la risposta supera ${chars} caratteri, parla Piper.`,
        keySet: "chiave impostata",
        keyMissing: "chiave mancante",
        apiKey: "Chiave API ElevenLabs",
        saveKey: "Salva la chiave",
        addWith: "Aggiungila con",
        cloudVoice: "Voce ElevenLabs",
        chooseVoice: "Scegli una voce",
        voiceId: "ID della voce",
        loadVoices: "Carica le voci",
        save: "Salva",
        cancel: "Annulla",
        preview: "Anteprima",
        sentence: "Frase",
        speaking: "Parlo…",
        listen: "Ascolta",
        saveFirst: "Salva per ascoltare la voce nuova.",
        firstTime: "La prima volta la voce viene scaricata: può volerci qualche secondo.",
        downloaded: "Modelli scaricati",
        recognitionModel: "riconoscimento",
        piperModel: "voce Piper",
        none: "Nessuno ancora: si scaricano al primo uso del microfono e della voce.",
    },
});

function StatusBadge({ status }: { status: VoiceStatus | null }) {
    const t = useText(TEXT);
    if (!status) {
        return null;
    }
    if (!status.enabled) {
        return <span className={styles.badge}>{t.off}</span>;
    }
    if (status.missing.length) {
        return (
            <span className={styles.badge} data-tone="warn">
                {t.missing(status.missing.join(", "))}
            </span>
        );
    }
    return (
        <span className={styles.badge} data-tone="ok">
            {t.on}
        </span>
    );
}

export default function VoicePage() {
    const lang = useLanguage();
    const t = TEXT[lang];
    const names = LANGUAGE_NAMES[lang];
    const { view, error, save } = useSettings();
    const desktop = useDesktopMode();
    const [status, setStatus] = useState<VoiceStatus | null>(null);
    const [form, setForm] = useState<VoiceForm | null>(null);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [note, setNote] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [key, setKey] = useState("");
    const [cloudVoices, setCloudVoices] = useState<CloudVoice[] | null>(null);
    const [cloudError, setCloudError] = useState<string | null>(null);
    // null: the sample sentence in the language of the chosen voice.
    const [previewText, setPreviewText] = useState<string | null>(null);
    const [previewing, setPreviewing] = useState(false);
    const [previewError, setPreviewError] = useState<string | null>(null);

    const saved = useMemo(() => (view ? voiceForm(view.settings) : null), [view]);
    const changes = useMemo(() => (saved && form ? voiceChanges(saved, form) : {}), [saved, form]);
    const dirty = Object.keys(changes).length > 0;

    const refreshStatus = useCallback(async () => {
        try {
            setStatus(await getJson<VoiceStatus>("/api/voice"));
        } catch {
            setStatus(null);
        }
    }, []);

    useEffect(() => {
        const first = setTimeout(refreshStatus, 0);
        return () => clearTimeout(first);
    }, [refreshStatus]);

    // The form starts from the saved values, and again after each save.
    useEffect(() => {
        if (saved) {
            const reset = setTimeout(() => setForm(saved), 0);
            return () => clearTimeout(reset);
        }
    }, [saved]);

    const set = (name: keyof VoiceForm, value: string) => {
        setForm((current) => (current ? { ...current, [name]: value } : current));
        setNote(null);
    };

    const submit = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!dirty) {
            return;
        }
        setBusy(true);
        const outcome = await save(changes);
        setBusy(false);
        setErrors(outcome.errors);
        setNote(
            outcome.ok ? t.saved : (outcome.message ?? t.notSaved)
        );
        if (outcome.ok) {
            void refreshStatus();
        }
    };

    const saveKey = async (name: "ELEVENLABS_API_KEY" | "XAI_API_KEY") => {
        if (!key.trim()) {
            return;
        }
        setBusy(true);
        try {
            await putJson("/api/desktop/secrets", { [name]: key.trim() });
            setKey("");
            setNote(t.keySaved);
            await refreshStatus();
        } catch (err) {
            setNote(err instanceof ApiError ? err.message : message(err));
        } finally {
            setBusy(false);
        }
    };

    const loadCloudVoices = async () => {
        setCloudError(null);
        try {
            const result = await getJson<{ voices: CloudVoice[] }>("/api/voice/elevenlabs/voices");
            setCloudVoices(result.voices);
        } catch (err) {
            setCloudVoices(null);
            setCloudError(message(err));
        }
    };

    const voiceLanguage = form ? piperLanguage(form.AEHUB_TTS_VOICE) : null;
    const sample = sampleSentence(
        form?.AEHUB_TTS_ENGINE === "elevenlabs"
            ? null
            : form?.AEHUB_TTS_ENGINE === "spacexai"
              ? form.AEHUB_SPACEXAI_LANGUAGE
              : voiceLanguage,
        lang,
    );

    const preview = async () => {
        setPreviewing(true);
        setPreviewError(null);
        try {
            const spoken = await postJson<{ audio_base64: string; audio_mime: string }>(
                "/api/voice/speak",
                {
                    text: (previewText ?? "").trim() || sample,
                    preview: true,
                }
            );
            if (spoken.audio_base64) {
                await playReply(spoken.audio_base64, () => undefined);
            }
            void refreshStatus();
        } catch (err) {
            setPreviewError(message(err));
        } finally {
            setPreviewing(false);
        }
    };

    if (error) {
        return (
            <main className={styles.page}>
                <p className={styles.error}>
                    {t.unavailable} {error}
                </p>
            </main>
        );
    }

    if (!view || !form) {
        return (
            <main className={styles.page}>
                <p className={styles.muted}>{t.loading}</p>
            </main>
        );
    }

    const eleven = form.AEHUB_TTS_ENGINE === "elevenlabs";
    const spacex = form.AEHUB_TTS_ENGINE === "spacexai";
    const cloud = eleven || spacex;
    const perMillion = status?.tts.spacexai_usd_per_million_chars ?? 15;
    const money = (value: number) =>
        value.toLocaleString(lang === "it" ? "it-IT" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const keyField = (name: "ELEVENLABS_API_KEY" | "XAI_API_KEY", label: string, isSet: boolean) => (
        <div className={styles.row}>
            <span className={styles.badge} data-tone={isSet ? "ok" : "warn"}>
                {isSet ? t.keySet : t.keyMissing}
            </span>
            {desktop ? (
                <>
                    <label className={styles.field}>
                        {label}
                        <input
                            type="password"
                            autoComplete="off"
                            value={key}
                            onChange={(event) => setKey(event.target.value)}
                        />
                    </label>
                    <button
                        type="button"
                        className={styles.btn}
                        onClick={() => saveKey(name)}
                        disabled={busy || !key.trim()}
                    >
                        {t.saveKey}
                    </button>
                </>
            ) : (
                !isSet && (
                    <span className={styles.muted}>
                        {t.addWith} <code className={styles.mono}>python scripts/aehub.py setup</code>.
                    </span>
                )
            )}
        </div>
    );
    const models = sttModels(lang);
    const sttInfo = models[form.AEHUB_STT_MODEL];
    const voiceIssues = view.issues.filter((issue) => issue.code.startsWith("voice"));
    const fieldError = (name: string) =>
        errors[name] ? (
            <span className={styles.error} role="alert">
                {errors[name]}
            </span>
        ) : null;

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>{t.title}</h1>
                <StatusBadge status={status} />
            </div>

            {voiceIssues.map((issue) => (
                <p
                    key={issue.code}
                    className={issue.severity === "error" ? styles.error : styles.warn}
                >
                    {issueText(issue, lang)}
                </p>
            ))}

            <form onSubmit={submit} className={styles.stack} aria-label={t.form}>
                <section className={styles.card}>
                    <h2 className={styles.h2}>{t.power}</h2>
                    <div className={styles.filters}>
                        <label className={styles.field}>
                            {t.voice}
                            <select
                                value={form.AEHUB_VOICE || "local"}
                                onChange={(event) => set("AEHUB_VOICE", event.target.value)}
                            >
                                <option value="local">{t.voiceOn}</option>
                                <option value="off">{t.voiceOff}</option>
                            </select>
                        </label>
                        <label className={styles.field}>
                            {t.idle}
                            <input
                                type="number"
                                min={0}
                                max={1440}
                                value={form.AEHUB_VOICE_IDLE_MINUTES}
                                onChange={(event) =>
                                    set("AEHUB_VOICE_IDLE_MINUTES", event.target.value)
                                }
                            />
                        </label>
                    </div>
                    <p className={styles.help}>{t.idleHelp}</p>
                    {fieldError("AEHUB_VOICE")}
                    {fieldError("AEHUB_VOICE_IDLE_MINUTES")}
                </section>

                <section className={styles.card}>
                    <h2 className={styles.h2}>{t.recognition}</h2>
                    <div className={styles.filters}>
                        <label className={styles.field}>
                            {t.model}
                            <select
                                value={form.AEHUB_STT_MODEL}
                                onChange={(event) => set("AEHUB_STT_MODEL", event.target.value)}
                            >
                                {Object.entries(models).map(([name, info]) => (
                                    <option key={name} value={name}>
                                        {name} · {info.label}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label className={styles.field}>
                            {t.language}
                            <select
                                value={form.AEHUB_STT_LANGUAGE}
                                onChange={(event) => set("AEHUB_STT_LANGUAGE", event.target.value)}
                            >
                                {Object.entries(LANGUAGES[lang]).map(([code, label]) => (
                                    <option key={code} value={code}>
                                        {label}
                                    </option>
                                ))}
                            </select>
                        </label>
                    </div>
                    {sttInfo && (
                        <p className={styles.muted}>{t.sttInfo(sttInfo.download, sttInfo.ram)}</p>
                    )}
                    {fieldError("AEHUB_STT_MODEL")}
                    {fieldError("AEHUB_STT_LANGUAGE")}
                </section>

                <section className={styles.card}>
                    <h2 className={styles.h2}>{t.replyVoice}</h2>
                    <div className={styles.row} role="radiogroup" aria-label={t.engine}>
                        <label className={styles.check}>
                            <input
                                type="radio"
                                name="engine"
                                checked={!cloud}
                                onChange={() => set("AEHUB_TTS_ENGINE", "piper")}
                            />
                            {t.piper}
                        </label>
                        <label className={styles.check}>
                            <input
                                type="radio"
                                name="engine"
                                checked={eleven}
                                onChange={() => set("AEHUB_TTS_ENGINE", "elevenlabs")}
                            />
                            {t.elevenlabs}
                        </label>
                        <label className={styles.check}>
                            <input
                                type="radio"
                                name="engine"
                                checked={spacex}
                                onChange={() => set("AEHUB_TTS_ENGINE", "spacexai")}
                            />
                            {t.spacexai}
                        </label>
                    </div>

                    <div className={styles.filters}>
                        <label className={`${styles.field} ${styles.grow}`}>
                            {cloud ? t.piperFallback : t.piperVoice}
                            <input
                                list="piper-voices"
                                value={form.AEHUB_TTS_VOICE}
                                onChange={(event) => set("AEHUB_TTS_VOICE", event.target.value)}
                                spellCheck={false}
                            />
                            <datalist id="piper-voices">
                                {PIPER_VOICES.map((name) => (
                                    <option key={name} value={name} />
                                ))}
                            </datalist>
                        </label>
                    </div>
                    {!cloud && (
                        <p className={styles.muted}>
                            {voiceLanguage ? t.speaks(names[voiceLanguage] ?? voiceLanguage) : t.speaksUnknown}
                        </p>
                    )}
                    {fieldError("AEHUB_TTS_VOICE")}

                    {spacex && (
                        <div className={styles.stack}>
                            <p className={styles.warn}>{t.spacexaiWarning(status?.tts.max_cloud_chars ?? 2500)}</p>
                            {keyField("XAI_API_KEY", t.spacexaiKey, Boolean(status?.tts.spacexai_key))}
                            <div className={styles.filters}>
                                <label className={`${styles.field} ${styles.grow}`}>
                                    {t.spacexaiVoice}
                                    <select
                                        value={form.AEHUB_SPACEXAI_VOICE || "eve"}
                                        onChange={(event) => set("AEHUB_SPACEXAI_VOICE", event.target.value)}
                                    >
                                        {Object.entries(SPACEXAI_VOICES[lang]).map(([name, label]) => (
                                            <option key={name} value={name}>
                                                {label}
                                            </option>
                                        ))}
                                    </select>
                                </label>
                                <label className={styles.field}>
                                    {t.spacexaiLanguage}
                                    <select
                                        value={form.AEHUB_SPACEXAI_LANGUAGE || "it"}
                                        onChange={(event) => set("AEHUB_SPACEXAI_LANGUAGE", event.target.value)}
                                    >
                                        {SPACEXAI_LANGUAGES.map((code) => (
                                            <option key={code} value={code}>
                                                {names[code] ?? code} ({code})
                                            </option>
                                        ))}
                                    </select>
                                </label>
                            </div>
                            <p className={styles.muted}>
                                {t.speaks(names[form.AEHUB_SPACEXAI_LANGUAGE] ?? form.AEHUB_SPACEXAI_LANGUAGE)}
                            </p>
                            <p className={styles.muted}>
                                {t.spacexaiPrice(
                                    money(perMillion),
                                    money(spacexaiMonthlyCost(10, 500, perMillion)),
                                    money(spacexaiMonthlyCost(100, 500, perMillion)),
                                )}
                            </p>
                            {fieldError("AEHUB_SPACEXAI_VOICE")}
                            {fieldError("AEHUB_SPACEXAI_LANGUAGE")}
                        </div>
                    )}

                    {eleven && (
                        <div className={styles.stack}>
                            <p className={styles.warn}>{t.cloudWarning(status?.tts.max_cloud_chars ?? 2500)}</p>
                            {keyField("ELEVENLABS_API_KEY", t.apiKey, Boolean(status?.tts.elevenlabs_key))}

                            <div className={styles.filters}>
                                <label className={`${styles.field} ${styles.grow}`}>
                                    {t.cloudVoice}
                                    {cloudVoices ? (
                                        <select
                                            value={form.AEHUB_ELEVENLABS_VOICE}
                                            onChange={(event) =>
                                                set("AEHUB_ELEVENLABS_VOICE", event.target.value)
                                            }
                                        >
                                            <option value="">{t.chooseVoice}</option>
                                            {cloudVoices.map((voice) => (
                                                <option key={voice.id} value={voice.id}>
                                                    {voice.name}
                                                    {voice.labels ? ` · ${voice.labels}` : ""}
                                                </option>
                                            ))}
                                        </select>
                                    ) : (
                                        <input
                                            value={form.AEHUB_ELEVENLABS_VOICE}
                                            placeholder={t.voiceId}
                                            onChange={(event) =>
                                                set("AEHUB_ELEVENLABS_VOICE", event.target.value)
                                            }
                                            spellCheck={false}
                                        />
                                    )}
                                </label>
                                <button
                                    type="button"
                                    className={styles.btn}
                                    onClick={loadCloudVoices}
                                    disabled={!status?.tts.elevenlabs_key}
                                >
                                    {t.loadVoices}
                                </button>
                                <label className={styles.field}>
                                    {t.model}
                                    <select
                                        value={form.AEHUB_ELEVENLABS_MODEL}
                                        onChange={(event) =>
                                            set("AEHUB_ELEVENLABS_MODEL", event.target.value)
                                        }
                                    >
                                        {Object.entries(ELEVENLABS_MODELS[lang]).map(([name, label]) => (
                                            <option key={name} value={name}>
                                                {label}
                                            </option>
                                        ))}
                                        {!(form.AEHUB_ELEVENLABS_MODEL in ELEVENLABS_MODELS[lang]) && (
                                            <option value={form.AEHUB_ELEVENLABS_MODEL}>
                                                {form.AEHUB_ELEVENLABS_MODEL}
                                            </option>
                                        )}
                                    </select>
                                </label>
                            </div>
                            {cloudError && <p className={styles.error}>{cloudError}</p>}
                            {fieldError("AEHUB_ELEVENLABS_VOICE")}
                            {fieldError("AEHUB_ELEVENLABS_MODEL")}
                        </div>
                    )}
                </section>

                <div className={styles.row}>
                    <button
                        type="submit"
                        className={`${styles.btn} ${styles.go}`}
                        disabled={busy || !dirty}
                    >
                        {t.save}
                    </button>
                    {dirty && (
                        <button
                            type="button"
                            className={styles.btn}
                            onClick={() => saved && setForm(saved)}
                        >
                            {t.cancel}
                        </button>
                    )}
                    {note && (
                        <span className={styles.muted} role="status">
                            {note}
                        </span>
                    )}
                </div>
            </form>

            <section className={styles.card}>
                <h2 className={styles.h2}>{t.preview}</h2>
                <div className={styles.filters}>
                    <label className={`${styles.field} ${styles.grow}`}>
                        {t.sentence}
                        <input
                            value={previewText ?? sample}
                            maxLength={300}
                            onChange={(event) => setPreviewText(event.target.value)}
                        />
                    </label>
                    <button
                        type="button"
                        className={styles.btn}
                        onClick={preview}
                        disabled={previewing || dirty || !status?.enabled}
                    >
                        {previewing ? t.speaking : t.listen}
                    </button>
                </div>
                <p className={styles.muted}>
                    {dirty ? t.saveFirst : t.firstTime}
                </p>
                {previewError && (
                    <p className={styles.error} role="alert">
                        {previewError}
                    </p>
                )}
            </section>

            <section className={styles.card}>
                <h2 className={styles.h2}>{t.downloaded}</h2>
                {status && (status.downloaded.whisper.length || status.downloaded.piper.length) ? (
                    <ul className={styles.lines}>
                        {status.downloaded.whisper.map((model) => (
                            <li key={`w-${model.name}`}>
                                <span>
                                    {t.recognitionModel} · {model.name}
                                </span>
                                <b>{formatBytes(model.bytes, lang)}</b>
                            </li>
                        ))}
                        {status.downloaded.piper.map((model) => (
                            <li key={`p-${model.name}`}>
                                <span>
                                    {t.piperModel} · {model.name}
                                </span>
                                <b>{formatBytes(model.bytes, lang)}</b>
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p className={styles.muted}>{t.none}</p>
                )}
            </section>
        </main>
    );
}
