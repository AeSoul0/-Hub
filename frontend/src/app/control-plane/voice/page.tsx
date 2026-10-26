/**
 * @file frontend/src/app/control-plane/voice/page.tsx
 * @description Voice (F3, ADR-021, ADR-024): speech recognition model and
 * language, the voice of the replies (Piper on this computer or, optional,
 * ElevenLabs), a preview, and the speech models already on disk.
 *
 * Reads GET /api/voice and the "voice" group of GET /api/settings; saves
 * through PUT /api/settings (applied to the next sentence, no restart). The
 * ElevenLabs key goes to the OS keyring (PUT /api/desktop/secrets) and is
 * never shown again. The preview is POST /api/voice/speak with preview=true.
 */
"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

import { useDesktopMode } from "@/components/control-plane/DesktopKeys";
import styles from "@/components/control-plane/control.module.css";
import { ApiError, getJson, postJson, putJson } from "@/lib/api/client";
import { useSettings } from "@/lib/api/settings";
import { playReply } from "@/lib/nucleo/audio";
import {
    ELEVENLABS_MODELS,
    formatBytes,
    LANGUAGES,
    PIPER_VOICES,
    PREVIEW_TEXT,
    STT_MODELS,
    voiceChanges,
    voiceForm,
    type CloudVoice,
    type VoiceForm,
    type VoiceStatus,
} from "@/lib/nucleo/voice";

function message(err: unknown): string {
    return err instanceof Error ? err.message : String(err);
}

function StatusBadge({ status }: { status: VoiceStatus | null }) {
    if (!status) {
        return null;
    }
    if (!status.enabled) {
        return <span className={styles.badge}>spenta</span>;
    }
    if (status.missing.length) {
        return (
            <span className={styles.badge} data-tone="warn">
                mancano {status.missing.join(", ")}
            </span>
        );
    }
    return (
        <span className={styles.badge} data-tone="ok">
            attiva
        </span>
    );
}

export default function VoicePage() {
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
    const [previewText, setPreviewText] = useState(PREVIEW_TEXT);
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
        setNote(outcome.ok ? "Salvato: vale dalla prossima frase." : outcome.message ?? "Non salvato.");
        if (outcome.ok) {
            void refreshStatus();
        }
    };

    const saveKey = async () => {
        if (!key.trim()) {
            return;
        }
        setBusy(true);
        try {
            await putJson("/api/desktop/secrets", { ELEVENLABS_API_KEY: key.trim() });
            setKey("");
            setNote("Chiave salvata nel portachiavi del sistema.");
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

    const preview = async () => {
        setPreviewing(true);
        setPreviewError(null);
        try {
            const spoken = await postJson<{ audio_base64: string; audio_mime: string }>("/api/voice/speak", {
                text: previewText.trim() || PREVIEW_TEXT,
                preview: true,
            });
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
                <p className={styles.error}>Impostazioni non disponibili: {error}</p>
            </main>
        );
    }

    if (!view || !form) {
        return (
            <main className={styles.page}>
                <p className={styles.muted}>Carico la voce…</p>
            </main>
        );
    }

    const cloud = form.AEHUB_TTS_ENGINE === "elevenlabs";
    const sttInfo = STT_MODELS[form.AEHUB_STT_MODEL];
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
                <h1 className={styles.title}>VOCE</h1>
                <StatusBadge status={status} />
            </div>

            {voiceIssues.map((issue) => (
                <p key={issue.code} className={issue.severity === "error" ? styles.error : styles.warn}>
                    {issue.message}
                </p>
            ))}

            <form onSubmit={submit} className={styles.stack} aria-label="Impostazioni della voce">
                <section className={styles.card}>
                    <h2 className={styles.h2}>Riconoscimento vocale</h2>
                    <div className={styles.filters}>
                        <label className={styles.field}>
                            Modello
                            <select
                                value={form.AEHUB_STT_MODEL}
                                onChange={(event) => set("AEHUB_STT_MODEL", event.target.value)}
                            >
                                {Object.entries(STT_MODELS).map(([name, info]) => (
                                    <option key={name} value={name}>
                                        {name} · {info.label}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label className={styles.field}>
                            Lingua
                            <select
                                value={form.AEHUB_STT_LANGUAGE}
                                onChange={(event) => set("AEHUB_STT_LANGUAGE", event.target.value)}
                            >
                                {Object.entries(LANGUAGES).map(([code, label]) => (
                                    <option key={code} value={code}>
                                        {label}
                                    </option>
                                ))}
                            </select>
                        </label>
                    </div>
                    {sttInfo && (
                        <p className={styles.muted}>
                            Download {sttInfo.download} la prima volta, RAM {sttInfo.ram} mentre trascrive. Gira
                            su questo computer: l&apos;audio non esce mai.
                        </p>
                    )}
                    {fieldError("AEHUB_STT_MODEL")}
                    {fieldError("AEHUB_STT_LANGUAGE")}
                </section>

                <section className={styles.card}>
                    <h2 className={styles.h2}>Voce delle risposte</h2>
                    <div className={styles.row} role="radiogroup" aria-label="Motore della voce">
                        <label className={styles.check}>
                            <input
                                type="radio"
                                name="engine"
                                checked={!cloud}
                                onChange={() => set("AEHUB_TTS_ENGINE", "piper")}
                            />
                            Piper · su questo computer
                        </label>
                        <label className={styles.check}>
                            <input
                                type="radio"
                                name="engine"
                                checked={cloud}
                                onChange={() => set("AEHUB_TTS_ENGINE", "elevenlabs")}
                            />
                            ElevenLabs · nel cloud
                        </label>
                    </div>

                    <div className={styles.filters}>
                        <label className={`${styles.field} ${styles.grow}`}>
                            {cloud ? "Voce Piper di riserva" : "Voce Piper"}
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
                    {fieldError("AEHUB_TTS_VOICE")}

                    {cloud && (
                        <div className={styles.stack}>
                            <p className={styles.warn}>
                                Con ElevenLabs il testo delle risposte va ai suoi server per diventare voce; il
                                microfono resta locale. Se il cloud non risponde, o la risposta supera{" "}
                                {status?.tts.max_cloud_chars ?? 2500} caratteri, parla Piper.
                            </p>

                            <div className={styles.row}>
                                <span className={styles.badge} data-tone={status?.tts.elevenlabs_key ? "ok" : "warn"}>
                                    {status?.tts.elevenlabs_key ? "chiave impostata" : "chiave mancante"}
                                </span>
                                {desktop ? (
                                    <>
                                        <label className={styles.field}>
                                            Chiave API ElevenLabs
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
                                            onClick={saveKey}
                                            disabled={busy || !key.trim()}
                                        >
                                            Salva la chiave
                                        </button>
                                    </>
                                ) : (
                                    !status?.tts.elevenlabs_key && (
                                        <span className={styles.muted}>
                                            Aggiungila con <code className={styles.mono}>python scripts/aehub.py setup</code>.
                                        </span>
                                    )
                                )}
                            </div>

                            <div className={styles.filters}>
                                <label className={`${styles.field} ${styles.grow}`}>
                                    Voce ElevenLabs
                                    {cloudVoices ? (
                                        <select
                                            value={form.AEHUB_ELEVENLABS_VOICE}
                                            onChange={(event) => set("AEHUB_ELEVENLABS_VOICE", event.target.value)}
                                        >
                                            <option value="">Scegli una voce</option>
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
                                            placeholder="ID della voce"
                                            onChange={(event) => set("AEHUB_ELEVENLABS_VOICE", event.target.value)}
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
                                    Carica le voci
                                </button>
                                <label className={styles.field}>
                                    Modello
                                    <select
                                        value={form.AEHUB_ELEVENLABS_MODEL}
                                        onChange={(event) => set("AEHUB_ELEVENLABS_MODEL", event.target.value)}
                                    >
                                        {Object.entries(ELEVENLABS_MODELS).map(([name, label]) => (
                                            <option key={name} value={name}>
                                                {label}
                                            </option>
                                        ))}
                                        {!(form.AEHUB_ELEVENLABS_MODEL in ELEVENLABS_MODELS) && (
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
                    <button type="submit" className={`${styles.btn} ${styles.go}`} disabled={busy || !dirty}>
                        Salva
                    </button>
                    {dirty && (
                        <button type="button" className={styles.btn} onClick={() => saved && setForm(saved)}>
                            Annulla
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
                <h2 className={styles.h2}>Anteprima</h2>
                <div className={styles.filters}>
                    <label className={`${styles.field} ${styles.grow}`}>
                        Frase
                        <input
                            value={previewText}
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
                        {previewing ? "Parlo…" : "Ascolta"}
                    </button>
                </div>
                <p className={styles.muted}>
                    {dirty
                        ? "Salva per ascoltare la voce nuova."
                        : "La prima volta la voce viene scaricata: può volerci qualche secondo."}
                </p>
                {previewError && (
                    <p className={styles.error} role="alert">
                        {previewError}
                    </p>
                )}
            </section>

            <section className={styles.card}>
                <h2 className={styles.h2}>Modelli scaricati</h2>
                {status && (status.downloaded.whisper.length || status.downloaded.piper.length) ? (
                    <ul className={styles.lines}>
                        {status.downloaded.whisper.map((model) => (
                            <li key={`w-${model.name}`}>
                                <span>riconoscimento · {model.name}</span>
                                <b>{formatBytes(model.bytes)}</b>
                            </li>
                        ))}
                        {status.downloaded.piper.map((model) => (
                            <li key={`p-${model.name}`}>
                                <span>voce Piper · {model.name}</span>
                                <b>{formatBytes(model.bytes)}</b>
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p className={styles.muted}>Nessuno ancora: si scaricano al primo uso del microfono e della voce.</p>
                )}
            </section>
        </main>
    );
}
