/**
 * @file frontend/src/app/control-plane/setup/page.tsx
 * @description First-run setup (M12, spec 5.4; Nucleo style in F4): keys and
 * working folder, models, prices, budget, then a final check. Each step saves
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

const STEPS = ["Chiavi e cartella", "Modelli", "Prezzi", "Budget", "Controllo"] as const;

const MODEL_FIELDS = ["OPENAI_MODEL", "AEHUB_CHECKER_MODEL"];
const BUDGET_FIELDS = ["AEHUB_MONTHLY_BUDGET", "AEHUB_RUN_MAX_COST", "AEHUB_BUDGET_WARNING_RATIO"];

export default function SetupPage() {
    const { view, error, refresh, save, finishOnboarding } = useSettings();
    const [step, setStep] = useState(0);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [message, setMessage] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const desktop = useDesktopMode();

    if (!view) {
        return (
            <main className={styles.page}>
                <p className={error ? styles.error : styles.muted}>{error ?? "Carico…"}</p>
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
        setStep((current) => Math.min(current + 1, STEPS.length - 1));
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

    const pick = (names: string[]) =>
        names
            .map((name) => view.settings.find((field) => field.name === name))
            .filter((field): field is SettingField => Boolean(field));

    if (view.onboarding.completed) {
        return (
            <main className={styles.page}>
                <h1 className={styles.title}>PRIMO AVVIO COMPLETATO</h1>
                <p className={styles.muted}>
                    ÆHub è pronto. Chiedigli qualcosa dal Nucleo: ogni azione rischiosa si ferma finché non decidi tu.
                </p>
                <div className={styles.row}>
                    <Link href="/" className={`${styles.btn} ${styles.go}`}>
                        Apri il Nucleo
                    </Link>
                    <Link href="/control-plane/approvals" className={styles.link}>
                        Approvazioni
                    </Link>
                    <Link href="/control-plane/settings" className={styles.link}>
                        Impostazioni
                    </Link>
                </div>
            </main>
        );
    }

    return (
        <main className={styles.page}>
            <div className={styles.stack} style={{ gap: 8 }}>
                <h1 className={styles.title}>PRIMO AVVIO</h1>
                <p className={styles.muted}>Una decina di minuti. Tutto si può cambiare dopo nelle Impostazioni.</p>
            </div>

            <ol className={styles.steps} aria-label="Passi del primo avvio">
                {STEPS.map((label, index) => (
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
                        <h2 className={styles.h2}>Chiavi</h2>
                        <SecretList secrets={view.secrets} desktop={desktop} />
                        {desktop && <DesktopKeys secrets={view.secrets} onSaved={() => void refresh()} />}
                        {!hasModelKey && (
                            <p className={styles.warn}>
                                Manca ancora una chiave di un provider di modelli: l&apos;agente non può partire
                                finché non ne aggiungi una (o non usi un server locale).
                            </p>
                        )}
                    </div>
                    <div className={`${styles.card} ${styles.section}`}>
                        <h2 className={styles.h2}>Cartella di lavoro</h2>
                        <p className={styles.muted}>
                            <span className={styles.mono}>{view.workspace.path}</span>{" "}
                            <span className={styles.badge} data-tone={view.workspace.exists ? "ok" : "bad"}>
                                {view.workspace.exists ? "esiste" : "mancante"}
                            </span>
                        </p>
                        <p className={styles.help}>L&apos;unico posto dove l&apos;agente legge e scrive file.</p>
                    </div>
                    <div className={styles.row}>
                        <button type="button" onClick={() => void refresh()} className={styles.btn}>
                            Ricontrolla
                        </button>
                        <button type="button" onClick={next} className={`${styles.btn} ${styles.go}`}>
                            Continua
                        </button>
                    </div>
                </section>
            )}

            {step === 1 && (
                <section className={styles.stack}>
                    <div className={`${styles.card} ${styles.section}`}>
                        <h2 className={styles.h2}>Modelli</h2>
                        <p className={styles.help}>
                            Il modello predefinito fa il lavoro; il Critic, il supervisore, controlla il risultato e
                            deve essere un modello diverso.
                        </p>
                        <SettingsForm
                            key={version}
                            fields={pick(MODEL_FIELDS)}
                            errors={errors}
                            busy={busy}
                            onSave={(changes) => void saveAndContinue(changes)}
                            submitLabel="Salva e continua"
                        />
                    </div>
                    <details className={`${styles.card} ${styles.details}`}>
                        <summary>UN MODELLO PER OGNI RUOLO (FACOLTATIVO)</summary>
                        <RoleEditor key={version} view={view} busy={busy} onSave={(changes) => void saveOnly(changes)} />
                    </details>
                </section>
            )}

            {step === 2 && (
                <section className={`${styles.card} ${styles.section}`}>
                    <h2 className={styles.h2}>Prezzi</h2>
                    <p className={styles.help}>
                        Dal listino del provider. Senza prezzo il costo si stima alto, così il budget ferma le run prima
                        e non dopo.
                    </p>
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
                            Salta per ora
                        </button>
                    </div>
                </section>
            )}

            {step === 3 && (
                <section className={`${styles.card} ${styles.section}`}>
                    <h2 className={styles.h2}>Budget</h2>
                    <SettingsForm
                        key={version}
                        fields={pick(BUDGET_FIELDS)}
                        errors={errors}
                        busy={busy}
                        onSave={(changes) => void saveAndContinue(changes)}
                        submitLabel="Salva e continua"
                    />
                </section>
            )}

            {step === 4 && (
                <section className={styles.stack}>
                    <h2 className={styles.h2}>Controllo</h2>
                    <IssueList issues={view.issues} />
                    <div className={styles.row}>
                        <button
                            type="button"
                            onClick={() => void finish()}
                            disabled={busy || !view.ready}
                            className={`${styles.btn} ${styles.go}`}
                        >
                            Finisci il primo avvio
                        </button>
                        {!view.ready && <span className={styles.muted}>Prima risolvi quello che blocca le run.</span>}
                    </div>
                </section>
            )}
        </main>
    );
}
