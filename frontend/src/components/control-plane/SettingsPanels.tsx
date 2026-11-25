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
import { SECRET_TEXT } from "@/lib/nucleo/models";

const SEVERITY: Record<Severity, { label: string; tone: string }> = {
    error: { label: "blocca le run", tone: "bad" },
    warning: { label: "da controllare", tone: "warn" },
    info: { label: "nota", tone: "" },
};

const ORDER: Severity[] = ["error", "warning", "info"];

export function IssueList({ issues }: { issues: ConfigIssue[] }) {
    if (issues.length === 0) {
        return <p className={styles.muted}>La configurazione non ha problemi.</p>;
    }

    const ordered = [...issues].sort((a, b) => ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity));

    return (
        <ul className={`${styles.plain} ${styles.stack}`} style={{ gap: 8 }} aria-label="Problemi della configurazione">
            {ordered.map((issue) => (
                <li key={issue.code} className={styles.issue} data-tone={SEVERITY[issue.severity].tone || undefined}>
                    <span className={styles.badge} data-tone={SEVERITY[issue.severity].tone || undefined}>
                        {SEVERITY[issue.severity].label}
                    </span>
                    <span>{issue.message}</span>
                </li>
            ))}
        </ul>
    );
}

export function SecretList({ secrets, desktop = false }: { secrets: SecretStatus[]; desktop?: boolean }) {
    return (
        <div className={styles.stack} style={{ gap: 10 }}>
            <ul className={styles.lines} aria-label="Chiavi">
                {secrets.map((secret) => {
                    const text = SECRET_TEXT[secret.name] ?? { label: secret.label, use: secret.used_for };
                    return (
                        <li key={secret.name}>
                            <span>
                                <b>{text.label}</b> · {text.use}
                            </span>
                            <span className={styles.badge} data-tone={secret.configured ? "ok" : undefined}>
                                {secret.configured ? "impostata" : "mancante"}
                            </span>
                        </li>
                    );
                })}
            </ul>
            {desktop ? (
                <p className={styles.help}>
                    Le chiavi restano nel portachiavi del sistema e non si rivedono più: scrivine una nuova qui sotto
                    per sostituirla.
                </p>
            ) : (
                <p className={styles.help}>
                    Le chiavi restano nel portachiavi del sistema, mai nel browser o in un file. Per aggiungerne o
                    cambiarne una: <code className={styles.mono}>python scripts/aehub.py setup</code>, poi{" "}
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
    const [rows, setRows] = useState<PriceRows>(() =>
        Object.fromEntries(models.map((entry) => [entry.model, priceOf(pricesJson, entry.model)])),
    );

    if (models.length === 0) {
        return <p className={styles.muted}>Scegli prima i modelli.</p>;
    }

    const update = (model: string, side: "input" | "output", value: string) =>
        setRows((current) => ({ ...current, [model]: { ...current[model], [side]: value } }));

    const fillable = models.filter((entry) => catalog[entry.model] && !rows[entry.model]?.input && !rows[entry.model]?.output);

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
                            <th>Modello</th>
                            <th>Input · USD per 1M token</th>
                            <th>Output · USD per 1M token</th>
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
                                            aria-label={`Prezzo ${side} di ${entry.model}`}
                                            inputMode="decimal"
                                            value={rows[entry.model]?.[side] ?? ""}
                                            placeholder={catalog[entry.model] ? String(catalog[entry.model][side]) : ""}
                                            onChange={(event) => update(entry.model, side, event.target.value)}
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
                    Salva i prezzi
                </button>
                {fillable.length > 0 && (
                    <button type="button" className={styles.btn} onClick={fill}>
                        Usa i prezzi di OpenRouter ({fillable.length})
                    </button>
                )}
            </div>
        </form>
    );
}
