/**
 * @file frontend/src/app/control-plane/setup/page.tsx
 * @description First-run setup (M12, spec 5.4; Nucleo style in F4): the
 * interface language (ADR-034), keys and working folder, models, prices,
 * budget, then a final check. Each step saves
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
import { IssueList, PriceTable, SecretList, type PriceRows } from "@/components/control-plane/SettingsPanels";
import styles from "@/components/control-plane/control.module.css";
import { mergePrices, useSettings, type SettingChanges, type SettingField } from "@/lib/api/settings";
import { LANGS, catalog, chooseLanguage, useLanguage, type Lang } from "@/lib/i18n";

const TEXT = catalog({
    en: {
        steps: ["Keys and folder", "Models", "Prices", "Budget", "Check"],
        loading: "Loading…",
        doneTitle: "FIRST START DONE",
        done: "ÆHub is ready. Ask it something from the Nucleo: every risky action stops until you decide.",
        openNucleo: "Open the Nucleo",
        approvals: "Approvals",
        settings: "Settings",
        title: "FIRST START",
        intro: "About ten minutes. Everything can be changed later in Settings.",
        stepsLabel: "Steps of the first start",
        language: "Language",
        languageHelp: "The language of the pages. It can be changed later in Settings, or by asking Aurora.",
        keys: "Keys",
        noModelKey:
            "A key of a model provider is still missing: the agent cannot start until you add one (or use a local server).",
        workspace: "Working folder",
        exists: "exists",
        missing: "missing",
        workspaceHelp: "The only place where the agent reads and writes files.",
        recheck: "Check again",
        continue: "Continue",
        models: "Models",
        modelsHelp: "The default model does the work; the Critic, the supervisor, checks the result and must be a different model.",
        saveContinue: "Save and continue",
        perRole: "ONE MODEL FOR EACH ROLE (OPTIONAL)",
        prices: "Prices",
        pricesHelp:
            "From the provider's price list. Without a price the cost is estimated high, so the budget stops runs early rather than late.",
        skip: "Skip for now",
        budget: "Budget",
        check: "Check",
        finish: "Finish the first start",
        solveFirst: "First solve what blocks the runs.",
    },
    it: {
        steps: ["Chiavi e cartella", "Modelli", "Prezzi", "Budget", "Controllo"],
        loading: "Carico…",
        doneTitle: "PRIMO AVVIO COMPLETATO",
        done: "ÆHub è pronto. Chiedigli qualcosa dal Nucleo: ogni azione rischiosa si ferma finché non decidi tu.",
        openNucleo: "Apri il Nucleo",
        approvals: "Approvazioni",
        settings: "Impostazioni",
        title: "PRIMO AVVIO",
        intro: "Una decina di minuti. Tutto si può cambiare dopo nelle Impostazioni.",
        stepsLabel: "Passi del primo avvio",
        language: "Lingua",
        languageHelp: "La lingua delle pagine. Si cambia dopo nelle Impostazioni, o chiedendolo ad Aurora.",
        keys: "Chiavi",
        noModelKey:
            "Manca ancora una chiave di un provider di modelli: l'agente non può partire finché non ne aggiungi una (o non usi un server locale).",
        workspace: "Cartella di lavoro",
        exists: "esiste",
        missing: "mancante",
        workspaceHelp: "L'unico posto dove l'agente legge e scrive file.",
        recheck: "Ricontrolla",
        continue: "Continua",
        models: "Modelli",
        modelsHelp:
            "Il modello predefinito fa il lavoro; il Critic, il supervisore, controlla il risultato e deve essere un modello diverso.",
        saveContinue: "Salva e continua",
        perRole: "UN MODELLO PER OGNI RUOLO (FACOLTATIVO)",
        prices: "Prezzi",
        pricesHelp:
            "Dal listino del provider. Senza prezzo il costo si stima alto, così il budget ferma le run prima e non dopo.",
        skip: "Salta per ora",
        budget: "Budget",
        check: "Controllo",
        finish: "Finisci il primo avvio",
        solveFirst: "Prima risolvi quello che blocca le run.",
    },
});

const STEP_COUNT = 5;

const MODEL_FIELDS = ["OPENAI_MODEL", "AEHUB_CHECKER_MODEL"];
const BUDGET_FIELDS = ["AEHUB_MONTHLY_BUDGET", "AEHUB_RUN_MAX_COST", "AEHUB_BUDGET_WARNING_RATIO"];

export default function SetupPage() {
    const lang = useLanguage();
    const t = TEXT[lang];
    const { view, error, refresh, save, finishOnboarding } = useSettings();
    const [step, setStep] = useState(0);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [message, setMessage] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const desktop = useDesktopMode();

    if (!view) {
        return (
            <main className={styles.page}>
                <p className={error ? styles.error : styles.muted}>{error ?? t.loading}</p>
            </main>
        );
    }

    const version = view.settings.map((field) => `${field.name}=${field.value}:${field.source}`).join("|");
    const pricesJson = view.settings.find((field) => field.name === "AEHUB_MODEL_PRICES")?.value ?? "";
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
                        {!hasModelKey && (
                            <p className={styles.warn}>{t.noModelKey}</p>
                        )}
                    </div>
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
                    <div className={styles.row}>
                        <button type="button" onClick={() => void refresh()} className={styles.btn}>
                            {t.recheck}
                        </button>
                        <button type="button" onClick={next} className={`${styles.btn} ${styles.go}`}>
                            {t.continue}
                        </button>
                    </div>
                </section>
            )}

            {step === 1 && (
                <section className={styles.stack}>
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
                </section>
            )}

            {step === 2 && (
                <section className={`${styles.card} ${styles.section}`}>
                    <h2 className={styles.h2}>{t.prices}</h2>
                    <p className={styles.help}>{t.pricesHelp}</p>
                    <PriceTable
                        key={version}
                        models={view.models}
                        pricesJson={pricesJson}
                        busy={busy}
                        onSave={(rows: PriceRows) =>
                            void saveAndContinue({ AEHUB_MODEL_PRICES: mergePrices(pricesJson, rows) })
                        }
                    />
                    {errors.AEHUB_MODEL_PRICES && <p className={styles.error}>{errors.AEHUB_MODEL_PRICES}</p>}
                    <div className={styles.row}>
                        <button type="button" onClick={next} className={styles.linkBtn}>
                            {t.skip}
                        </button>
                    </div>
                </section>
            )}

            {step === 3 && (
                <section className={`${styles.card} ${styles.section}`}>
                    <h2 className={styles.h2}>{t.budget}</h2>
                    <SettingsForm
                        key={version}
                        fields={pick(BUDGET_FIELDS)}
                        errors={errors}
                        busy={busy}
                        onSave={(changes) => void saveAndContinue(changes)}
                        submitLabel={t.saveContinue}
                    />
                </section>
            )}

            {step === 4 && (
                <section className={styles.stack}>
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
                    </div>
                </section>
            )}
        </main>
    );
}
