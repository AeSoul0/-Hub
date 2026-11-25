/**
 * @file frontend/src/components/control-plane/SettingsPanels.tsx
 * @description Parts of Settings and the first-run setup (M12, restyled in
 * F4): configuration issues, which keys are set (never their values), and
 * the price table of the models the routing can call, which can take the
 * prices OpenRouter publishes.
 */
import React, { useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import type { ConfigIssue, RoutedModel, SecretStatus, Severity } from "@/lib/api/settings";
import { catalog as textCatalog, useLanguage, useText } from "@/lib/i18n";
import { SECRET_TEXT, issueText } from "@/lib/nucleo/models";

const TONES: Record<Severity, string> = { error: "bad", warning: "warn", info: "" };

const TEXT = textCatalog({
    en: {
        severity: { error: "stops runs", warning: "to check", info: "note" } as Record<Severity, string>,
        noIssues: "The configuration has no problems.",
        issues: "Configuration problems",
        keys: "Keys",
        set: "set",
        missing: "missing",
        desktopHelp: "Keys stay in the system keyring and cannot be seen again: write a new one below to replace it.",
        keyringHelp: "Keys stay in the system keyring, never in the browser or a file. To add or change one:",
        then: ", then",
        chooseModels: "Choose the models first.",
        model: "Model",
        inputPrice: "Input · USD per 1M tokens",
        outputPrice: "Output · USD per 1M tokens",
        priceOf: (side: string, model: string) => `${side === "input" ? "Input" : "Output"} price of ${model}`,
        savePrices: "Save the prices",
        useOpenRouter: (count: number) => `Use the OpenRouter prices (${count})`,
    },
    it: {
        severity: { error: "blocca le run", warning: "da controllare", info: "nota" } as Record<Severity, string>,
        noIssues: "La configurazione non ha problemi.",
        issues: "Problemi della configurazione",
        keys: "Chiavi",
        set: "impostata",
        missing: "mancante",
        desktopHelp:
            "Le chiavi restano nel portachiavi del sistema e non si rivedono più: scrivine una nuova qui sotto per sostituirla.",
        keyringHelp:
            "Le chiavi restano nel portachiavi del sistema, mai nel browser o in un file. Per aggiungerne o cambiarne una:",
        then: ", poi",
        chooseModels: "Scegli prima i modelli.",
        model: "Modello",
        inputPrice: "Input · USD per 1M token",
        outputPrice: "Output · USD per 1M token",
        priceOf: (side: string, model: string) => `Prezzo ${side} di ${model}`,
        savePrices: "Salva i prezzi",
        useOpenRouter: (count: number) => `Usa i prezzi di OpenRouter (${count})`,
    },
});

const ORDER: Severity[] = ["error", "warning", "info"];

export function IssueList({ issues }: { issues: ConfigIssue[] }) {
    const lang = useLanguage();
    const t = TEXT[lang];

    if (issues.length === 0) {
        return <p className={styles.muted}>{t.noIssues}</p>;
    }

    const ordered = [...issues].sort(
        (a, b) => ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity)
    );

    return (
        <ul
            className={`${styles.plain} ${styles.stack}`}
            style={{ gap: 8 }}
            aria-label={t.issues}
        >
            {ordered.map((issue) => (
                <li
                    key={issue.code}
                    className={styles.issue}
                    data-tone={TONES[issue.severity] || undefined}
                >
                    <span
                        className={styles.badge}
                        data-tone={TONES[issue.severity] || undefined}
                    >
                        {t.severity[issue.severity]}
                    </span>
                    <span>{issueText(issue, lang)}</span>
                </li>
            ))}
        </ul>
    );
}

export function SecretList({
    secrets,
    desktop = false,
}: {
    secrets: SecretStatus[];
    desktop?: boolean;
}) {
    const lang = useLanguage();
    const t = TEXT[lang];

    return (
        <div className={styles.stack} style={{ gap: 10 }}>
            <ul className={styles.lines} aria-label={t.keys}>
                {secrets.map((secret) => {
                    const text = SECRET_TEXT[lang][secret.name] ?? {
                        label: secret.label,
                        use: secret.used_for,
                    };
                    return (
                        <li key={secret.name}>
                            <span>
                                <b>{text.label}</b> · {text.use}
                            </span>
                            <span
                                className={styles.badge}
                                data-tone={secret.configured ? "ok" : undefined}
                            >
                                {secret.configured ? t.set : t.missing}
                            </span>
                        </li>
                    );
                })}
            </ul>
            {desktop ? (
                <p className={styles.help}>{t.desktopHelp}</p>
            ) : (
                <p className={styles.help}>
                    {t.keyringHelp} <code className={styles.mono}>python scripts/aehub.py setup</code>
                    {t.then}{" "}
                    <code className={styles.mono}>python scripts/aehub.py up</code>.
                </p>
            )}
        </div>
    );
}

export type PriceRows = Record<string, { input: string; output: string }>;
export type CatalogPrices = Record<string, { input: number; output: number }>;

/** Current price of a model from the AEHUB_MODEL_PRICES JSON, if any. */
function priceOf(pricesJson: string, model: string): { input: string; output: string } {
    try {
        const price = JSON.parse(pricesJson || "{}")[model];
        if (price) {
            return { input: String(price.input), output: String(price.output) };
        }
    } catch {
        // Invalid JSON: start empty.
    }
    return { input: "", output: "" };
}

export function PriceTable({
    models,
    pricesJson,
    busy,
    onSave,
    catalog = {},
}: {
    models: RoutedModel[];
    pricesJson: string;
    busy: boolean;
    onSave: (rows: PriceRows) => void;
    /** Prices published by the provider (OpenRouter), USD per 1M tokens. */
    catalog?: CatalogPrices;
}) {
    const t = useText(TEXT);
    const [rows, setRows] = useState<PriceRows>(() =>
        Object.fromEntries(models.map((entry) => [entry.model, priceOf(pricesJson, entry.model)]))
    );

    if (models.length === 0) {
        return <p className={styles.muted}>{t.chooseModels}</p>;
    }

    const update = (model: string, side: "input" | "output", value: string) =>
        setRows((current) => ({ ...current, [model]: { ...current[model], [side]: value } }));

    const fillable = models.filter(
        (entry) => catalog[entry.model] && !rows[entry.model]?.input && !rows[entry.model]?.output
    );

    const fill = () =>
        setRows((current) => {
            const next = { ...current };
            for (const entry of fillable) {
                const price = catalog[entry.model];
                next[entry.model] = { input: String(price.input), output: String(price.output) };
            }
            return next;
        });

    return (
        <form
            className={styles.stack}
            style={{ gap: 12 }}
            onSubmit={(event) => {
                event.preventDefault();
                onSave(rows);
            }}
        >
            <div className={styles.tableWrap}>
                <table className={styles.table}>
                    <thead>
                        <tr>
                            <th>{t.model}</th>
                            <th>{t.inputPrice}</th>
                            <th>{t.outputPrice}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {models.map((entry) => (
                            <tr key={entry.model}>
                                <td>
                                    <span className={styles.mono}>{entry.model}</span>
                                    <span className={styles.sub}>{entry.roles.join(", ")}</span>
                                </td>
                                {(["input", "output"] as const).map((side) => (
                                    <td key={side}>
                                        <input
                                            aria-label={t.priceOf(side, entry.model)}
                                            inputMode="decimal"
                                            value={rows[entry.model]?.[side] ?? ""}
                                            placeholder={
                                                catalog[entry.model]
                                                    ? String(catalog[entry.model][side])
                                                    : ""
                                            }
                                            onChange={(event) =>
                                                update(entry.model, side, event.target.value)
                                            }
                                            className={`${styles.input} ${styles.narrow}`}
                                        />
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <div className={styles.row}>
                <button type="submit" disabled={busy} className={`${styles.btn} ${styles.go}`}>
                    {t.savePrices}
                </button>
                {fillable.length > 0 && (
                    <button type="button" className={styles.btn} onClick={fill}>
                        {t.useOpenRouter(fillable.length)}
                    </button>
                )}
            </div>
        </form>
    );
}
