/**
 * @file frontend/src/app/control-plane/settings/page.tsx
 * @description Settings (M12, F4): keys, the LLM of each role with its
 * fallbacks, default models and the local server, prices, budget and
 * limits, and the engine's tuning, in the Nucleo's style. Changes apply
 * without a restart: the next run uses them, a run already going keeps what
 * it started with. Keys are shown only as set or not set.
 */
"use client";

import Link from "next/link";
import React, { useMemo, useState } from "react";

import DesktopKeys, { useDesktopMode } from "@/components/control-plane/DesktopKeys";
import RoleEditor from "@/components/control-plane/RoleEditor";
import SettingsForm from "@/components/control-plane/SettingsForm";
import {
    IssueList,
    PriceTable,
    SecretList,
    type CatalogPrices,
    type PriceRows,
} from "@/components/control-plane/SettingsPanels";
import styles from "@/components/control-plane/control.module.css";
import {
    mergePrices,
    useProviderModels,
    useSettings,
    type SettingChanges,
    type SettingField,
} from "@/lib/api/settings";

const DEFAULT_MODELS = ["OPENAI_MODEL", "AEHUB_CHECKER_MODEL", "AEHUB_FORCE_ROLE", "AEHUB_LOCAL_BASE_URL"];
// Written by the role editor and the price table; editable as JSON under "avanzate".
const JSON_FIELDS = ["AEHUB_MODEL_ROLES", "AEHUB_MODEL_PRICES"];

export default function SettingsPage() {
    const { view, error, refresh, save } = useSettings();
    const desktop = useDesktopMode();
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
    const [busy, setBusy] = useState(false);
    const { models: catalog } = useProviderModels(["openrouter"]);

    const catalogPrices: CatalogPrices = useMemo(
        () =>
            Object.fromEntries(
                (catalog.openrouter ?? [])
                    .filter((model) => model.price)
                    .map((model) => [model.id, model.price as { input: number; output: number }]),
            ),
        [catalog.openrouter],
    );

    const apply = async (changes: SettingChanges) => {
        if (Object.keys(changes).length === 0) {
            return;
        }
        setBusy(true);
        const outcome = await save(changes);
        setBusy(false);
        setErrors(outcome.errors);
        setNotice(
            outcome.ok
                ? { ok: true, text: "Salvato: la prossima run usa queste impostazioni." }
                : { ok: false, text: outcome.message ?? "Non salvato." },
        );
    };

    if (!view) {
        return (
            <main className={styles.page}>
                <p className={error ? styles.error : styles.muted}>{error ?? "Carico le impostazioni…"}</p>
            </main>
        );
    }

    const version = view.settings.map((field) => `${field.name}=${field.value}:${field.source}`).join("|");
    const pricesJson = view.settings.find((field) => field.name === "AEHUB_MODEL_PRICES")?.value ?? "";
    const pick = (names: string[]) =>
        names
            .map((name) => view.settings.find((field) => field.name === name))
            .filter((field): field is SettingField => Boolean(field));
    const group = (name: SettingField["group"]) =>
        view.settings.filter((field) => field.group === name && !JSON_FIELDS.includes(field.name));

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>IMPOSTAZIONI</h1>
                {!view.onboarding.completed && (
                    <Link href="/control-plane/setup" className={styles.link}>
                        Completa il primo avvio →
                    </Link>
                )}
                <div className={styles.headEnd}>
                    <span className={styles.badge} data-tone={view.ready ? "ok" : "bad"}>
                        {view.ready ? "pronto" : "le run sono bloccate"}
                    </span>
                </div>
            </div>

            {notice && (
                <p className={notice.ok ? styles.muted : styles.error} role="status">
                    {notice.text}
                </p>
            )}

            <section className={styles.section}>
                <h2 className={styles.h2}>Controllo</h2>
                <IssueList issues={view.issues} />
            </section>

            <section className={`${styles.card} ${styles.section}`}>
                <h2 className={styles.h2}>Chiavi</h2>
                <SecretList secrets={view.secrets} desktop={desktop} />
                {desktop && <DesktopKeys secrets={view.secrets} onSaved={() => void refresh()} />}
            </section>

            <section className={styles.section}>
                <h2 className={styles.h2}>Modelli per ruolo</h2>
                <RoleEditor key={version} view={view} busy={busy} onSave={apply} error={errors.routing} />
            </section>

            <section className={`${styles.card} ${styles.section}`}>
                <h2 className={styles.h2}>Modelli predefiniti e server locale</h2>
                <SettingsForm key={version} fields={pick(DEFAULT_MODELS)} errors={errors} busy={busy} onSave={apply} />
            </section>

            <section className={`${styles.card} ${styles.section}`}>
                <h2 className={styles.h2}>Prezzi</h2>
                <p className={styles.help}>
                    Dal listino del provider. Senza prezzo il costo si stima alto, così il budget ferma le run prima e
                    non dopo.
                </p>
                <PriceTable
                    key={version}
                    models={view.models}
                    pricesJson={pricesJson}
                    busy={busy}
                    catalog={catalogPrices}
                    onSave={(rows: PriceRows) => void apply({ AEHUB_MODEL_PRICES: mergePrices(pricesJson, rows) })}
                />
                {errors.AEHUB_MODEL_PRICES && <p className={styles.error}>{errors.AEHUB_MODEL_PRICES}</p>}
                <SettingsForm key={`p-${version}`} fields={group("prices")} errors={errors} busy={busy} onSave={apply} />
            </section>

            <section className={`${styles.card} ${styles.section}`}>
                <h2 className={styles.h2}>Budget e limiti</h2>
                <SettingsForm key={version} fields={group("limits")} errors={errors} busy={busy} onSave={apply} />
            </section>

            <section className={`${styles.card} ${styles.section}`}>
                <h2 className={styles.h2}>Motore</h2>
                <SettingsForm key={version} fields={group("engine")} errors={errors} busy={busy} onSave={apply} />
            </section>

            <section className={`${styles.card} ${styles.section}`}>
                <h2 className={styles.h2}>Cartella di lavoro</h2>
                <p className={styles.muted}>
                    <span className={styles.mono}>{view.workspace.path}</span>{" "}
                    <span className={styles.badge} data-tone={view.workspace.exists ? "ok" : "bad"}>
                        {view.workspace.exists ? "esiste" : "mancante"}
                    </span>
                </p>
                <p className={styles.help}>
                    L&apos;agente legge e scrive file solo qui. La cartella si sceglie con{" "}
                    <code className={styles.mono}>python scripts/aehub.py setup</code>.
                </p>
            </section>

            <details className={`${styles.card} ${styles.details}`}>
                <summary>AVANZATE · JSON DEI RUOLI E DEI PREZZI</summary>
                <SettingsForm key={`j-${version}`} fields={pick(JSON_FIELDS)} errors={errors} busy={busy} onSave={apply} />
            </details>
        </main>
    );
}
