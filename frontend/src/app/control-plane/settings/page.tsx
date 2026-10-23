/**
 * @file frontend/src/app/control-plane/settings/page.tsx
 * @description Settings (M12): model roles, prices and limits, changed
 * without a restart. The next run uses them; a run already going keeps what
 * it started with. Keys are shown only as set or not set.
 */
"use client";

import Link from "next/link";
import React, { useState } from "react";

import SettingsForm from "@/components/control-plane/SettingsForm";
import { IssueList, PriceTable, SecretList, type PriceRows } from "@/components/control-plane/SettingsPanels";
import { mergePrices, useSettings, type SettingChanges, type SettingGroup } from "@/lib/api/settings";

const GROUPS: { group: SettingGroup; title: string }[] = [
    { group: "models", title: "Models" },
    { group: "prices", title: "Prices" },
    { group: "limits", title: "Budget and limits" },
];

export default function SettingsPage() {
    const { view, error, save } = useSettings();
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [notice, setNotice] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const apply = async (changes: SettingChanges) => {
        if (Object.keys(changes).length === 0) {
            return;
        }
        setBusy(true);
        const outcome = await save(changes);
        setBusy(false);
        setErrors(outcome.errors);
        setNotice(outcome.ok ? "Saved. The next run uses these settings." : outcome.message ?? null);
    };

    const savePrices = (rows: PriceRows) => {
        const current = view?.settings.find((field) => field.name === "AEHUB_MODEL_PRICES")?.value ?? "";
        void apply({ AEHUB_MODEL_PRICES: mergePrices(current, rows) });
    };

    if (!view) {
        return <div className="p-8 text-gray-400">{error ?? "Loading settings…"}</div>;
    }

    const version = view.settings.map((field) => `${field.name}=${field.value}:${field.source}`).join("|");
    const pricesJson = view.settings.find((field) => field.name === "AEHUB_MODEL_PRICES")?.value ?? "";

    return (
        <div className="p-8 space-y-8">
            <div className="flex flex-wrap items-baseline gap-4">
                <h1 className="text-3xl font-bold text-orange-500">Settings</h1>
                {!view.onboarding.completed && (
                    <Link href="/control-plane/setup" className="text-cyan-400 hover:text-cyan-300">
                        Finish the first-run setup →
                    </Link>
                )}
            </div>

            {notice && <p className={Object.keys(errors).length ? "text-red-400" : "text-green-400"}>{notice}</p>}
            {errors.routing && <p className="text-red-400">{errors.routing}</p>}

            <section>
                <h2 className="text-xl font-semibold mb-3">Configuration check</h2>
                <IssueList issues={view.issues} />
            </section>

            <section>
                <h2 className="text-xl font-semibold mb-3">Keys</h2>
                <SecretList secrets={view.secrets} />
            </section>

            {GROUPS.map(({ group, title }) => (
                <section key={group}>
                    <h2 className="text-xl font-semibold mb-3">{title}</h2>
                    {group === "prices" && (
                        <div className="mb-6">
                            <PriceTable
                                key={version}
                                models={view.models}
                                pricesJson={pricesJson}
                                busy={busy}
                                onSave={savePrices}
                            />
                        </div>
                    )}
                    <SettingsForm
                        key={version}
                        fields={view.settings.filter((field) => field.group === group)}
                        errors={errors}
                        busy={busy}
                        onSave={apply}
                    />
                </section>
            ))}

            <section>
                <h2 className="text-xl font-semibold mb-3">Working folder</h2>
                <p className="text-sm">
                    <span className="font-mono">{view.workspace.path}</span>{" "}
                    <span className={view.workspace.exists ? "text-green-400" : "text-red-400"}>
                        {view.workspace.exists ? "exists" : "missing"}
                    </span>
                </p>
                <p className="mt-1 text-xs text-gray-400">
                    The agent reads and writes files only here. Choose the folder on your computer with{" "}
                    <code className="text-gray-200">python scripts/aehub.py setup</code>.
                </p>
            </section>
        </div>
    );
}
