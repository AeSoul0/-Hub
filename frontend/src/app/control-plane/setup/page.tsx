/**
 * @file frontend/src/app/control-plane/setup/page.tsx
 * @description First-run setup (M12, spec 5.4): keys and working folder,
 * models, prices, budget, then a final check. Each step saves through the
 * Settings API, so nothing needs a restart; keys are added with the launcher
 * because they never pass through the browser, except in the desktop app,
 * which has no terminal: there they are typed once and go to the OS keyring.
 */
"use client";

import Link from "next/link";
import React, { useState } from "react";

import DesktopKeys, { useDesktopMode } from "@/components/control-plane/DesktopKeys";
import SettingsForm from "@/components/control-plane/SettingsForm";
import { IssueList, PriceTable, SecretList, type PriceRows } from "@/components/control-plane/SettingsPanels";
import { mergePrices, useSettings, type SettingChanges } from "@/lib/api/settings";

const STEPS = ["Keys and folder", "Models", "Prices", "Budget", "Check"] as const;

const MODEL_FIELDS = ["OPENAI_MODEL", "AEHUB_CHECKER_MODEL", "AEHUB_MODEL_ROLES"];
const BUDGET_FIELDS = ["AEHUB_MONTHLY_BUDGET", "AEHUB_RUN_MAX_COST", "AEHUB_BUDGET_WARNING_RATIO"];

export default function SetupPage() {
    const { view, error, refresh, save, finishOnboarding } = useSettings();
    const [step, setStep] = useState(0);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [message, setMessage] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const desktop = useDesktopMode();

    if (!view) {
        return <div className="p-8 text-gray-400">{error ?? "Loading…"}</div>;
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

    const saveAndContinue = async (changes: SettingChanges) => {
        if (Object.keys(changes).length === 0) {
            next();
            return;
        }
        setBusy(true);
        const outcome = await save(changes);
        setBusy(false);
        if (outcome.ok) {
            next();
        } else {
            setErrors(outcome.errors);
            setMessage(outcome.message ?? null);
        }
    };

    const savePrices = (rows: PriceRows) =>
        saveAndContinue({ AEHUB_MODEL_PRICES: mergePrices(pricesJson, rows) });

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
            .filter((field): field is NonNullable<typeof field> => Boolean(field));

    if (view.onboarding.completed) {
        return (
            <div className="p-8 max-w-2xl space-y-4">
                <h1 className="text-3xl font-bold text-orange-500">Setup complete</h1>
                <p>
                    ÆHub is ready. Ask it something from the assistant; anything risky stops in Approvals until you
                    decide.
                </p>
                <div className="flex gap-4">
                    <Link href="/" className="bg-orange-600 hover:bg-orange-500 rounded px-4 py-1">
                        Open the assistant
                    </Link>
                    <Link href="/control-plane/approvals" className="text-cyan-400 hover:text-cyan-300 py-1">
                        Approvals
                    </Link>
                    <Link href="/control-plane/settings" className="text-cyan-400 hover:text-cyan-300 py-1">
                        Settings
                    </Link>
                </div>
            </div>
        );
    }

    return (
        <div className="p-8 max-w-3xl">
            <h1 className="text-3xl font-bold mb-2 text-orange-500">First-run setup</h1>
            <p className="mb-6 text-gray-400">About ten minutes. Everything can be changed later in Settings.</p>

            <ol className="flex flex-wrap gap-2 mb-8 text-sm" aria-label="Setup steps">
                {STEPS.map((label, index) => (
                    <li key={label}>
                        <button
                            onClick={() => setStep(index)}
                            aria-current={index === step ? "step" : undefined}
                            className={`px-3 py-1 rounded ${
                                index === step ? "bg-orange-600 text-white" : "bg-gray-900 text-gray-300"
                            }`}
                        >
                            {index + 1}. {label}
                        </button>
                    </li>
                ))}
            </ol>

            {message && <p className="mb-4 text-red-400">{message}</p>}
            {errors.routing && <p className="mb-4 text-red-400">{errors.routing}</p>}

            {step === 0 && (
                <section className="space-y-6">
                    <div>
                        <h2 className="text-xl font-semibold mb-3">Keys</h2>
                        <SecretList secrets={view.secrets} desktop={desktop} />
                        {desktop && <DesktopKeys onSaved={() => void refresh()} />}
                        {!hasModelKey && (
                            <p className="mt-3 text-yellow-300">
                                No model provider key yet: the agent cannot run until you add one.
                            </p>
                        )}
                    </div>
                    <div>
                        <h2 className="text-xl font-semibold mb-2">Working folder</h2>
                        <p className="text-sm">
                            <span className="font-mono">{view.workspace.path}</span>{" "}
                            <span className={view.workspace.exists ? "text-green-400" : "text-red-400"}>
                                {view.workspace.exists ? "exists" : "missing"}
                            </span>
                        </p>
                        <p className="mt-1 text-xs text-gray-400">
                            The only place where the agent reads and writes files.
                        </p>
                    </div>
                    <div className="flex gap-4">
                        <button onClick={() => void refresh()} className="text-cyan-400 hover:text-cyan-300">
                            Check again
                        </button>
                        <button onClick={next} className="bg-orange-600 hover:bg-orange-500 rounded px-4 py-1">
                            Continue
                        </button>
                    </div>
                </section>
            )}

            {step === 1 && (
                <section>
                    <h2 className="text-xl font-semibold mb-2">Models</h2>
                    <p className="mb-4 text-sm text-gray-400">
                        The Worker does the task; the Critic reviews the result and must be a different model.
                    </p>
                    <SettingsForm
                        key={version}
                        fields={pick(MODEL_FIELDS)}
                        errors={errors}
                        busy={busy}
                        onSave={saveAndContinue}
                        submitLabel="Save and continue"
                    />
                </section>
            )}

            {step === 2 && (
                <section>
                    <h2 className="text-xl font-semibold mb-2">Prices</h2>
                    <p className="mb-4 text-sm text-gray-400">
                        From your provider&apos;s price list. Without a price, cost is estimated high, so the budget
                        stops runs early rather than late.
                    </p>
                    <PriceTable
                        key={version}
                        models={view.models}
                        pricesJson={pricesJson}
                        busy={busy}
                        onSave={savePrices}
                    />
                    {errors.AEHUB_MODEL_PRICES && <p className="mt-2 text-red-400">{errors.AEHUB_MODEL_PRICES}</p>}
                    <button onClick={next} className="mt-4 text-sm text-gray-400 hover:text-white">
                        Skip for now
                    </button>
                </section>
            )}

            {step === 3 && (
                <section>
                    <h2 className="text-xl font-semibold mb-4">Budget</h2>
                    <SettingsForm
                        key={version}
                        fields={pick(BUDGET_FIELDS)}
                        errors={errors}
                        busy={busy}
                        onSave={saveAndContinue}
                        submitLabel="Save and continue"
                    />
                </section>
            )}

            {step === 4 && (
                <section className="space-y-4">
                    <h2 className="text-xl font-semibold">Check</h2>
                    <IssueList issues={view.issues} />
                    <button
                        onClick={() => void finish()}
                        disabled={busy || !view.ready}
                        className="bg-orange-600 hover:bg-orange-500 disabled:opacity-50 rounded px-4 py-1"
                    >
                        Finish setup
                    </button>
                    {!view.ready && (
                        <p className="text-sm text-gray-400">Fix what blocks runs first, then finish.</p>
                    )}
                </section>
            )}
        </div>
    );
}
