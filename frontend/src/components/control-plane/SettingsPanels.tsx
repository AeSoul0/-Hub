/**
 * @file frontend/src/components/control-plane/SettingsPanels.tsx
 * @description Read-only parts of Settings and the first-run setup (M12):
 * configuration issues, which keys are set, and a price table for the models
 * the routing can call.
 */
import React, { useState } from "react";

import type { ConfigIssue, RoutedModel, SecretStatus, Severity } from "@/lib/api/settings";

const SEVERITY_STYLE: Record<Severity, string> = {
    error: "border-red-700 bg-red-950 text-red-200",
    warning: "border-yellow-700 bg-yellow-950 text-yellow-100",
    info: "border-gray-700 bg-gray-900 text-gray-300",
};

const SEVERITY_LABEL: Record<Severity, string> = {
    error: "Blocks runs",
    warning: "Check",
    info: "Note",
};

export function IssueList({ issues }: { issues: ConfigIssue[] }) {
    if (issues.length === 0) {
        return <p className="text-green-400">The configuration has no problems.</p>;
    }

    const ordered = [...issues].sort(
        (a, b) => ["error", "warning", "info"].indexOf(a.severity) - ["error", "warning", "info"].indexOf(b.severity),
    );

    return (
        <ul className="space-y-2" aria-label="Configuration issues">
            {ordered.map((issue) => (
                <li key={issue.code} className={`border rounded p-3 text-sm ${SEVERITY_STYLE[issue.severity]}`}>
                    <span className="mr-2 text-xs uppercase font-bold">{SEVERITY_LABEL[issue.severity]}</span>
                    {issue.message}
                </li>
            ))}
        </ul>
    );
}

export function SecretList({ secrets }: { secrets: SecretStatus[] }) {
    return (
        <div>
            <ul className="space-y-1 text-sm" aria-label="Keys">
                {secrets.map((secret) => (
                    <li key={secret.name} className="flex flex-wrap gap-2 items-baseline">
                        <span
                            className={`text-xs px-2 rounded ${
                                secret.configured ? "bg-green-900 text-green-200" : "bg-gray-800 text-gray-400"
                            }`}
                        >
                            {secret.configured ? "set" : "not set"}
                        </span>
                        <span className="font-mono">{secret.name}</span>
                        <span className="text-gray-400">— {secret.used_for}</span>
                    </li>
                ))}
            </ul>
            <p className="mt-3 text-xs text-gray-400">
                Keys stay in the OS keyring, never in the browser or in a file. To add or change one, run{" "}
                <code className="text-gray-200">python scripts/aehub.py setup</code>, then restart with{" "}
                <code className="text-gray-200">python scripts/aehub.py up</code>.
            </p>
        </div>
    );
}

export type PriceRows = Record<string, { input: string; output: string }>;

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
}: {
    models: RoutedModel[];
    pricesJson: string;
    busy: boolean;
    onSave: (rows: PriceRows) => void;
}) {
    const [rows, setRows] = useState<PriceRows>(() =>
        Object.fromEntries(models.map((entry) => [entry.model, priceOf(pricesJson, entry.model)])),
    );

    if (models.length === 0) {
        return <p className="text-gray-400">Choose the models first.</p>;
    }

    const update = (model: string, side: "input" | "output", value: string) =>
        setRows((current) => ({ ...current, [model]: { ...current[model], [side]: value } }));

    return (
        <form
            onSubmit={(event) => {
                event.preventDefault();
                onSave(rows);
            }}
        >
            <table className="text-sm mb-3">
                <thead>
                    <tr className="text-left text-gray-400">
                        <th className="pr-4 font-normal">Model</th>
                        <th className="pr-4 font-normal">Input, USD per 1M tokens</th>
                        <th className="font-normal">Output, USD per 1M tokens</th>
                    </tr>
                </thead>
                <tbody>
                    {models.map((entry) => (
                        <tr key={entry.model}>
                            <td className="pr-4 py-1">
                                <span className="font-mono">{entry.model}</span>
                                <span className="ml-2 text-xs text-gray-500">{entry.roles.join(", ")}</span>
                            </td>
                            {(["input", "output"] as const).map((side) => (
                                <td key={side} className="pr-4 py-1">
                                    <input
                                        aria-label={`${entry.model} ${side} price`}
                                        inputMode="decimal"
                                        value={rows[entry.model]?.[side] ?? ""}
                                        onChange={(event) => update(entry.model, side, event.target.value)}
                                        className="w-28 rounded bg-gray-900 border border-gray-700 px-2 py-1"
                                    />
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
            <button
                type="submit"
                disabled={busy}
                className="bg-orange-600 hover:bg-orange-500 disabled:opacity-50 rounded px-4 py-1"
            >
                Save prices
            </button>
        </form>
    );
}
