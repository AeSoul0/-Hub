/**
 * @file frontend/src/app/control-plane/setup/page.tsx
 * @description First-run setup in three steps (N6; M12, spec 5.4): the
 * model (language, key, default model and Critic), the folders, the voice
 * with the final check. Everything else keeps its default value: prices,
 * budget and a chain per role are in Settings, for later. Each step saves
 * through the Settings API, so nothing needs a restart; keys are added with
 * the launcher because they never pass through the browser, except in the
 * desktop app, which has no terminal: there they are typed once and go to
 * the OS keyring.
 */
"use client";

import Link from "next/link";
import React, { useState } from "react";

import DesktopKeys, { useDesktopMode } from "@/components/control-plane/DesktopKeys";
import RoleEditor from "@/components/control-plane/RoleEditor";
import SettingsForm from "@/components/control-plane/SettingsForm";
import { IssueList, SecretList } from "@/components/control-plane/SettingsPanels";
import styles from "@/components/control-plane/control.module.css";
import { useSettings, type SettingChanges, type SettingField } from "@/lib/api/settings";
import { absolutePath, foldersValue } from "@/lib/api/tools";
import { LANGS, catalog, chooseLanguage, useLanguage, type Lang } from "@/lib/i18n";

const TEXT = catalog({
    en: {
        steps: ["Model", "Folders", "Voice and check"],
        loading: "Loading…",
        doneTitle: "FIRST START DONE",
        done: "ÆHub is ready. Ask it something from the Nucleo: every risky action stops until you decide.",
        openNucleo: "Open the Nucleo",
        approvals: "Approvals",
        settings: "Settings",
        title: "FIRST START",
        intro: "Three steps, a few minutes. Prices, budget and the models of each role start from their defaults: they are in Settings when you want them.",
        stepsLabel: "Steps of the first start",
        language: "Language",
        languageHelp: "The language of the pages. It can be changed later in Settings, or by asking Aurora.",
        keys: "Model key",
        noModelKey:
            "A key of a model provider is still missing: the agent cannot start until you add one (or use a local server such as Ollama).",
        recheck: "Check again",
        continue: "Continue",
        models: "Models",
        modelsHelp: "The default model does the work; the Critic, the supervisor, checks the result and must be a different model.",
        saveContinue: "Save and continue",
        perRole: "ONE MODEL FOR EACH ROLE (OPTIONAL)",
        workspace: "Working folder",
        exists: "exists",
        missing: "missing",
        workspaceHelp: "Where the agent reads and writes files, and where screenshots and uploads go.",
        extraFolder: "Another folder for the agents (optional)",
        extraFolderHelp: "For example your Documents. More can be added on STRUMENTI; ÆHub's own files and hidden files stay out of reach.",
        folderInvalid: "Write a full path, such as C:\\Users\\me\\Documents or /home/me/Documents.",
        voice: "Voice",
        voiceHelp: "On: you speak to the Nucleo and it answers aloud, with models that run on this computer. The voice, the language and the wake word are on the VOCE page.",
        voiceOn: "On",
        voiceOff: "Off",
        voicePage: "Choose the voice",
        check: "Check",
        finish: "Finish the first start",
        solveFirst: "First solve what blocks the runs.",
    },
    it: {
        steps: ["Modello", "Cartelle", "Voce e controllo"],
        loading: "Carico…",
        doneTitle: "PRIMO AVVIO COMPLETATO",
        done: "ÆHub è pronto. Chiedigli qualcosa dal Nucleo: ogni azione rischiosa si ferma finché non decidi tu.",
        openNucleo: "Apri il Nucleo",
        approvals: "Approvazioni",
        settings: "Impostazioni",
        title: "PRIMO AVVIO",
        intro: "Tre passi, pochi minuti. Prezzi, budget e i modelli di ogni ruolo partono dai valori predefiniti: sono nelle Impostazioni quando li vuoi.",
        stepsLabel: "Passi del primo avvio",
        language: "Lingua",
        languageHelp: "La lingua delle pagine. Si cambia dopo nelle Impostazioni, o chiedendolo ad Aurora.",
        keys: "Chiave del modello",
        noModelKey:
            "Manca ancora una chiave di un provider di modelli: l'agente non può partire finché non ne aggiungi una (o non usi un server locale come Ollama).",
        recheck: "Ricontrolla",
        continue: "Continua",
        models: "Modelli",
        modelsHelp: "Il modello predefinito fa il lavoro; il Critic, il supervisore, controlla il risultato e deve essere un modello diverso.",
        saveContinue: "Salva e continua",
        perRole: "UN MODELLO PER OGNI RUOLO (FACOLTATIVO)",
        workspace: "Cartella di lavoro",
        exists: "esiste",
        missing: "mancante",
        workspaceHelp: "Dove l'agente legge e scrive file, e dove vanno gli screenshot e i caricamenti.",
        extraFolder: "Un'altra cartella per gli agenti (facoltativa)",
        extraFolderHelp: "Per esempio i tuoi Documenti. Altre si aggiungono su STRUMENTI; i file di ÆHub e i file nascosti restano fuori portata.",
        folderInvalid: "Scrivi un percorso completo, come C:\\Users\\me\\Documents o /home/me/Documents.",
        voice: "Voce",
        voiceHelp: "Accesa: parli al Nucleo e risponde a voce, con modelli che girano su questo computer. La voce, la lingua e la parola di attivazione sono nella pagina VOCE.",
        voiceOn: "Accesa",
        voiceOff: "Spenta",
        voicePage: "Scegli la voce",
        check: "Controllo",
        finish: "Finisci il primo avvio",
        solveFirst: "Prima risolvi quello che blocca le run.",
    },
});

const STEP_COUNT = 3;

const MODEL_FIELDS = ["OPENAI_MODEL", "AEHUB_CHECKER_MODEL"];

/** AEHUB_AGENT_FOLDERS with this folder first and the others already there after it. */
function withFirstFolder(settings: SettingField[], folder: string): string | null {
    const raw = settings.find((field) => field.name === "AEHUB_AGENT_FOLDERS")?.value ?? "";
    let rest: string[] = [];
    try {
        const folders: unknown = JSON.parse(raw || "[]");
        rest = Array.isArray(folders) ? folders.filter((item): item is string => typeof item === "string").slice(1) : [];
    } catch {
        rest = [];
    }
    return foldersValue([folder, ...rest]);
}

/** The first folder the owner already gave the agents, if any. */
function firstAgentFolder(settings: SettingField[]): string {
    const raw = settings.find((field) => field.name === "AEHUB_AGENT_FOLDERS")?.value ?? "";
    try {
        const folders: unknown = JSON.parse(raw || "[]");
        return Array.isArray(folders) && typeof folders[0] === "string" ? folders[0] : "";
    } catch {
        return "";
    }
}

export default function SetupPage() {
    const lang = useLanguage();
    const t = TEXT[lang];
    const { view, error, refresh, save, finishOnboarding } = useSettings();
    const [step, setStep] = useState(0);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [message, setMessage] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    // The folder typed in step 2; null until it is touched.
    const [folder, setFolder] = useState<string | null>(null);
    const desktop = useDesktopMode();

    if (!view) {
        return (
            <main className={styles.page}>
                <p className={error ? styles.error : styles.muted}>{error ?? t.loading}</p>
            </main>
        );
    }

    const version = view.settings.map((field) => `${field.name}=${field.value}:${field.source}`).join("|");
    const savedFolder = firstAgentFolder(view.settings);
    const folderText = folder ?? savedFolder;
    const folderValid = !folderText.trim() || absolutePath(folderText);
    const voiceOn = (view.settings.find((field) => field.name === "AEHUB_VOICE")?.value ?? "local") !== "off";
    const hasModelKey = view.secrets.some(
        (secret) => ["OPENAI_API_KEY", "OPENROUTER_API_KEY"].includes(secret.name) && secret.configured,
    );

    const next = () => {
        setErrors({});
        setMessage(null);
        setStep((current) => Math.min(current + 1, STEP_COUNT - 1));
    };

    const saveOnly = async (changes: SettingChanges) => {
        setBusy(true);
        const outcome = await save(changes);
        setBusy(false);
        setErrors(outcome.errors);
        setMessage(outcome.ok ? null : outcome.message ?? null);
        return outcome.ok;
    };

    const saveAndContinue = async (changes: SettingChanges) => {
        if (Object.keys(changes).length === 0 || (await saveOnly(changes))) {
            next();
        }
    };

    const finish = async () => {
        setBusy(true);
        const outcome = await finishOnboarding();
        setBusy(false);
        if (!outcome.ok) {
            setMessage(outcome.message ?? null);
            setErrors(outcome.errors);
        }
    };

    const switchLanguage = (next: Lang) => {
        chooseLanguage(next);
        void saveOnly({ AEHUB_UI_LANGUAGE: next });
    };

    const pick = (names: string[]) =>
        names
            .map((name) => view.settings.find((field) => field.name === name))
            .filter((field): field is SettingField => Boolean(field));

    if (view.onboarding.completed) {
        return (
            <main className={styles.page}>
                <h1 className={styles.title}>{t.doneTitle}</h1>
                <p className={styles.muted}>{t.done}</p>
                <div className={styles.row}>
                    <Link href="/" className={`${styles.btn} ${styles.go}`}>
                        {t.openNucleo}
                    </Link>
                    <Link href="/control-plane/approvals" className={styles.link}>
                        {t.approvals}
                    </Link>
                    <Link href="/control-plane/settings" className={styles.link}>
                        {t.settings}
                    </Link>
                </div>
            </main>
        );
    }

    return (
        <main className={styles.page}>
            <div className={styles.stack} style={{ gap: 8 }}>
                <h1 className={styles.title}>{t.title}</h1>
                <p className={styles.muted}>{t.intro}</p>
            </div>

            <ol className={styles.steps} aria-label={t.stepsLabel}>
                {t.steps.map((label, index) => (
                    <li key={label}>
                        <button type="button" onClick={() => setStep(index)} aria-current={index === step ? "step" : undefined}>
                            {index + 1}. {label}
                        </button>
                    </li>
                ))}
            </ol>

            {message && (
                <p className={styles.error} role="alert">
                    {message}
                </p>
            )}
            {errors.routing && (
                <p className={styles.error} role="alert">
                    {errors.routing}
                </p>
            )}

            {step === 0 && (
                <section className={styles.stack}>
                    <div className={`${styles.card} ${styles.section}`}>
                        <h2 className={styles.h2}>{t.language}</h2>
                        <div className={styles.row} role="radiogroup" aria-label={t.language}>
                            {LANGS.map((option) => (
                                <label key={option.value} className={styles.check} lang={option.value}>
                                    <input
                                        type="radio"
                                        name="setup-language"
                                        checked={lang === option.value}
                                        disabled={busy}
                                        onChange={() => switchLanguage(option.value)}
                                    />
                                    {option.label}
                                </label>
                            ))}
                        </div>
                        <p className={styles.help}>{t.languageHelp}</p>
                    </div>
                    <div className={`${styles.card} ${styles.section}`}>
                        <h2 className={styles.h2}>{t.keys}</h2>
                        <SecretList secrets={view.secrets} desktop={desktop} />
                        {desktop && <DesktopKeys secrets={view.secrets} onSaved={() => void refresh()} />}
                        {!hasModelKey && <p className={styles.warn}>{t.noModelKey}</p>}
                        <div className={styles.row}>
                            <button type="button" onClick={() => void refresh()} className={styles.btn}>
                                {t.recheck}
                            </button>
                        </div>
                    </div>
                    <div className={`${styles.card} ${styles.section}`}>
                        <h2 className={styles.h2}>{t.models}</h2>
                        <p className={styles.help}>{t.modelsHelp}</p>
                        <SettingsForm
                            key={version}
                            fields={pick(MODEL_FIELDS)}
                            errors={errors}
                            busy={busy}
                            onSave={(changes) => void saveAndContinue(changes)}
                            submitLabel={t.saveContinue}
                        />
                    </div>
                    <details className={`${styles.card} ${styles.details}`}>
                        <summary>{t.perRole}</summary>
                        <RoleEditor key={version} view={view} busy={busy} onSave={(changes) => void saveOnly(changes)} />
                    </details>
                    <div className={styles.row}>
                        <button type="button" onClick={next} className={`${styles.btn} ${styles.go}`}>
                            {t.continue}
                        </button>
                    </div>
                </section>
            )}

            {step === 1 && (
                <section className={styles.stack}>
                    <div className={`${styles.card} ${styles.section}`}>
                        <h2 className={styles.h2}>{t.workspace}</h2>
                        <p className={styles.muted}>
                            <span className={styles.mono}>{view.workspace.path}</span>{" "}
                            <span className={styles.badge} data-tone={view.workspace.exists ? "ok" : "bad"}>
                                {view.workspace.exists ? t.exists : t.missing}
                            </span>
                        </p>
                        <p className={styles.help}>{t.workspaceHelp}</p>
                    </div>
                    <form
                        className={`${styles.card} ${styles.section}`}
                        onSubmit={(event) => {
                            event.preventDefault();
                            if (!folderValid) {
                                return;
                            }
                            if (folderText.trim() === savedFolder.trim()) {
                                next();
                                return;
                            }
                            void saveAndContinue({ AEHUB_AGENT_FOLDERS: withFirstFolder(view.settings, folderText) });
                        }}
                    >
                        <label className={styles.h2} htmlFor="setup-folder">
                            {t.extraFolder}
                        </label>
                        <input
                            id="setup-folder"
                            className={styles.input}
                            value={folderText}
                            placeholder={"C:\\Users\\me\\Documents"}
                            spellCheck={false}
                            aria-invalid={!folderValid}
                            aria-describedby="setup-folder-help"
                            onChange={(event) => setFolder(event.target.value)}
                        />
                        <p className={styles.help} id="setup-folder-help">
                            {t.extraFolderHelp}
                        </p>
                        {!folderValid && (
                            <p className={styles.error} role="alert">
                                {t.folderInvalid}
                            </p>
                        )}
                        {errors.AEHUB_AGENT_FOLDERS && <p className={styles.error}>{errors.AEHUB_AGENT_FOLDERS}</p>}
                        <div className={styles.row}>
                            <button type="submit" disabled={busy || !folderValid} className={`${styles.btn} ${styles.go}`}>
                                {folderText.trim() === savedFolder.trim() ? t.continue : t.saveContinue}
                            </button>
                        </div>
                    </form>
                </section>
            )}

            {step === 2 && (
                <section className={styles.stack}>
                    <div className={`${styles.card} ${styles.section}`}>
                        <h2 className={styles.h2}>{t.voice}</h2>
                        <div className={styles.row} role="radiogroup" aria-label={t.voice}>
                            {[
                                { value: "local", label: t.voiceOn, on: true },
                                { value: "off", label: t.voiceOff, on: false },
                            ].map((option) => (
                                <label key={option.value} className={styles.check}>
                                    <input
                                        type="radio"
                                        name="setup-voice"
                                        checked={voiceOn === option.on}
                                        disabled={busy}
                                        onChange={() => void saveOnly({ AEHUB_VOICE: option.value })}
                                    />
                                    {option.label}
                                </label>
                            ))}
                        </div>
                        <p className={styles.help}>{t.voiceHelp}</p>
                        <div className={styles.row}>
                            <Link href="/control-plane/voice" className={styles.link}>
                                {t.voicePage}
                            </Link>
                        </div>
                    </div>
                    <div className={`${styles.card} ${styles.section}`}>
                        <h2 className={styles.h2}>{t.check}</h2>
                        <IssueList issues={view.issues} />
                        <div className={styles.row}>
                            <button
                                type="button"
                                onClick={() => void finish()}
                                disabled={busy || !view.ready}
                                className={`${styles.btn} ${styles.go}`}
                            >
                                {t.finish}
                            </button>
                            {!view.ready && <span className={styles.muted}>{t.solveFirst}</span>}
                            <Link href="/control-plane/settings" className={styles.link}>
                                {t.settings}
                            </Link>
                        </div>
                    </div>
                </section>
            )}
        </main>
    );
}
