/**
 * @file frontend/src/app/control-plane/settings/page.tsx
 * @description Settings (M12, F4): the interface language and the voice
 * language notice (ADR-034), keys, the LLM of each role with its
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
import { LANGS, catalog, chooseLanguage, chooseVoiceWarning, useLanguage, type Lang } from "@/lib/i18n";

const TEXT = catalog({
    en: {
        saved: "Saved: the next run uses these settings.",
        notSaved: "Not saved.",
        loading: "Loading the settings…",
        title: "SETTINGS",
        firstRun: "Finish the first start →",
        ready: "ready",
        blocked: "runs are blocked",
        language: "Language",
        languageHelp: "The language of the pages. Aurora can change it too, if you ask her.",
        languageSaved: "The interface is in English.",
        voiceNotice: "Warn me when the chosen voice speaks another language than the interface",
        voiceNoticeHelp: "The voice speaks the language of the voice you choose on the Voice page.",
        noticeOn: "The voice language notice is on.",
        noticeOff: "The voice language notice is off.",
        check: "Check",
        keys: "Keys",
        roles: "Models by role",
        defaults: "Default models and local server",
        prices: "Prices",
        pricesHelp:
            "From the provider's price list. Without a price the cost is estimated high, so the budget stops runs early rather than late.",
        limits: "Budget and limits",
        engine: "Engine",
        workspace: "Working folder",
        exists: "exists",
        missing: "missing",
        workspaceHelp: "The agent reads and writes files only here. The folder is chosen with",
        advanced: "ADVANCED · JSON OF ROLES AND PRICES",
    },
    it: {
        saved: "Salvato: la prossima run usa queste impostazioni.",
        notSaved: "Non salvato.",
        loading: "Carico le impostazioni…",
        title: "IMPOSTAZIONI",
        firstRun: "Completa il primo avvio →",
        ready: "pronto",
        blocked: "le run sono bloccate",
        language: "Lingua",
        languageHelp: "La lingua delle pagine. Può cambiarla anche Aurora, se glielo chiedi.",
        languageSaved: "L'interfaccia è in italiano.",
        voiceNotice: "Avvisami quando la voce scelta parla un'altra lingua dell'interfaccia",
        voiceNoticeHelp: "La voce parla la lingua della voce che scegli nella pagina Voce.",
        noticeOn: "L'avviso sulla lingua della voce è acceso.",
        noticeOff: "L'avviso sulla lingua della voce è spento.",
        check: "Controllo",
        keys: "Chiavi",
        roles: "Modelli per ruolo",
        defaults: "Modelli predefiniti e server locale",
        prices: "Prezzi",
        pricesHelp:
            "Dal listino del provider. Senza prezzo il costo si stima alto, così il budget ferma le run prima e non dopo.",
        limits: "Budget e limiti",
        engine: "Motore",
        workspace: "Cartella di lavoro",
        exists: "esiste",
        missing: "mancante",
        workspaceHelp: "L'agente legge e scrive file solo qui. La cartella si sceglie con",
        advanced: "AVANZATE · JSON DEI RUOLI E DEI PREZZI",
    },
});

const DEFAULT_MODELS = ["OPENAI_MODEL", "AEHUB_CHECKER_MODEL", "AEHUB_FORCE_ROLE", "AEHUB_LOCAL_BASE_URL"];
// Written by the role editor and the price table; editable as JSON under "advanced".
const JSON_FIELDS = ["AEHUB_MODEL_ROLES", "AEHUB_MODEL_PRICES"];

export default function SettingsPage() {
    const lang = useLanguage();
    const t = TEXT[lang];
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

    const apply = async (changes: SettingChanges, done?: string) => {
        if (Object.keys(changes).length === 0) {
            return;
        }
        setBusy(true);
        const outcome = await save(changes);
        setBusy(false);
        setErrors(outcome.errors);
        setNotice(
            outcome.ok
                ? { ok: true, text: done ?? TEXT[lang].saved }
                : { ok: false, text: outcome.message ?? TEXT[lang].notSaved },
        );
    };

    const switchLanguage = (next: Lang) => {
        // The pages switch at once; the backend keeps the choice for Aurora and every browser.
        chooseLanguage(next);
        void apply({ AEHUB_UI_LANGUAGE: next }, TEXT[next].languageSaved);
    };

    const switchNotice = (enabled: boolean) => {
        chooseVoiceWarning(enabled);
        void apply({ AEHUB_VOICE_LANGUAGE_WARNING: enabled ? "on" : "off" }, enabled ? t.noticeOn : t.noticeOff);
    };

    if (!view) {
        return (
            <main className={styles.page}>
                <p className={error ? styles.error : styles.muted}>{error ?? t.loading}</p>
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
    const valueOf = (name: string) => view.settings.find((field) => field.name === name)?.value;
    const noticeOn = (valueOf("AEHUB_VOICE_LANGUAGE_WARNING") ?? "on") !== "off";

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>{t.title}</h1>
                {!view.onboarding.completed && (
                    <Link href="/control-plane/setup" className={styles.link}>
                        {t.firstRun}
                    </Link>
                )}
                <div className={styles.headEnd}>
                    <span className={styles.badge} data-tone={view.ready ? "ok" : "bad"}>
                        {view.ready ? t.ready : t.blocked}
                    </span>
                </div>
            </div>

            {notice && (
                <p className={notice.ok ? styles.muted : styles.error} role="status">
                    {notice.text}
                </p>
            )}

            <section className={`${styles.card} ${styles.section}`} aria-label={t.language}>
                <h2 className={styles.h2}>{t.language}</h2>
                <p className={styles.help}>{t.languageHelp}</p>
                <div className={styles.row} role="radiogroup" aria-label={t.language}>
                    {LANGS.map((option) => (
                        <label key={option.value} className={styles.check} lang={option.value}>
                            <input
                                type="radio"
                                name="interface-language"
                                checked={lang === option.value}
                                disabled={busy}
                                onChange={() => switchLanguage(option.value)}
                            />
                            {option.label}
                        </label>
                    ))}
                </div>
                <label className={styles.check}>
                    <input
                        type="checkbox"
                        checked={noticeOn}
                        disabled={busy}
                        onChange={(event) => switchNotice(event.target.checked)}
                    />
                    {t.voiceNotice}
                </label>
                <p className={styles.help}>{t.voiceNoticeHelp}</p>
            </section>

            <section className={styles.section}>
                <h2 className={styles.h2}>{t.check}</h2>
                <IssueList issues={view.issues} />
            </section>

            <section className={`${styles.card} ${styles.section}`}>
                <h2 className={styles.h2}>{t.keys}</h2>
                <SecretList secrets={view.secrets} desktop={desktop} />
                {desktop && <DesktopKeys secrets={view.secrets} onSaved={() => void refresh()} />}
            </section>

            <section className={styles.section}>
                <h2 className={styles.h2}>{t.roles}</h2>
                <RoleEditor key={version} view={view} busy={busy} onSave={(changes) => void apply(changes)} error={errors.routing} />
            </section>

            <section className={`${styles.card} ${styles.section}`}>
                <h2 className={styles.h2}>{t.defaults}</h2>
                <SettingsForm key={version} fields={pick(DEFAULT_MODELS)} errors={errors} busy={busy} onSave={(changes) => void apply(changes)} />
            </section>

            <section className={`${styles.card} ${styles.section}`}>
                <h2 className={styles.h2}>{t.prices}</h2>
                <p className={styles.help}>{t.pricesHelp}</p>
                <PriceTable
                    key={version}
                    models={view.models}
                    pricesJson={pricesJson}
                    busy={busy}
                    catalog={catalogPrices}
                    onSave={(rows: PriceRows) => void apply({ AEHUB_MODEL_PRICES: mergePrices(pricesJson, rows) })}
                />
                {errors.AEHUB_MODEL_PRICES && <p className={styles.error}>{errors.AEHUB_MODEL_PRICES}</p>}
                <SettingsForm key={`p-${version}`} fields={group("prices")} errors={errors} busy={busy} onSave={(changes) => void apply(changes)} />
            </section>

            <section className={`${styles.card} ${styles.section}`}>
                <h2 className={styles.h2}>{t.limits}</h2>
                <SettingsForm key={version} fields={group("limits")} errors={errors} busy={busy} onSave={(changes) => void apply(changes)} />
            </section>

            <section className={`${styles.card} ${styles.section}`}>
                <h2 className={styles.h2}>{t.engine}</h2>
                <SettingsForm key={version} fields={group("engine")} errors={errors} busy={busy} onSave={(changes) => void apply(changes)} />
            </section>

            <section className={`${styles.card} ${styles.section}`}>
                <h2 className={styles.h2}>{t.workspace}</h2>
                <p className={styles.muted}>
                    <span className={styles.mono}>{view.workspace.path}</span>{" "}
                    <span className={styles.badge} data-tone={view.workspace.exists ? "ok" : "bad"}>
                        {view.workspace.exists ? t.exists : t.missing}
                    </span>
                </p>
                <p className={styles.help}>
                    {t.workspaceHelp}{" "}
                    <code className={styles.mono}>python scripts/aehub.py setup</code>.
                </p>
            </section>

            <details className={`${styles.card} ${styles.details}`}>
                <summary>{t.advanced}</summary>
                <SettingsForm key={`j-${version}`} fields={pick(JSON_FIELDS)} errors={errors} busy={busy} onSave={(changes) => void apply(changes)} />
            </details>
        </main>
    );
}
