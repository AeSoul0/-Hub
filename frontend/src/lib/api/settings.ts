/**
 * @file frontend/src/lib/api/settings.ts
 * @description Settings and first-run setup (M12): types and a hook over
 * GET/PUT /api/settings and POST /api/settings/onboarding.
 *
 * Secrets never come through here: the API only says whether each one is
 * set. They live in the OS keyring, managed by `python scripts/aehub.py`
 * (or typed once in the desktop app, PUT /api/desktop/secrets).
 */
"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, getJson, postJson, putJson } from "@/lib/api/client";

export type SettingGroup = "models" | "prices" | "limits" | "engine" | "voice" | "tools";
export type SettingKind = "text" | "roles" | "prices" | "price_pair" | "number" | "integer" | "ratio" | "choice";
export type SettingSource = "database" | "environment" | "default";
export type Severity = "error" | "warning" | "info";

export interface SettingField {
    name: string;
    group: SettingGroup;
    label: string;
    kind: SettingKind;
    help: string;
    default: string;
    value: string;
    source: SettingSource;
    /** The accepted values of a "choice" setting. */
    options?: string[];
}

export interface SecretStatus {
    name: string;
    label: string;
    used_for: string;
    configured: boolean;
}

export interface ConfigIssue {
    code: string;
    severity: Severity;
    message: string;
    setting: string | null;
}

export interface RoutedModel {
    model: string;
    providers: string[];
    roles: string[];
    priced: boolean;
}

export type RoleName = "architect" | "research" | "critic" | "fast_worker" | "triage";
export type ProviderName = "openai" | "openrouter" | "local";

/** A role's chain as the engine uses it now; custom when set in AEHUB_MODEL_ROLES. */
export interface RoleChain {
    chain: string[];
    custom: boolean;
}

export interface ProviderState {
    key: boolean;
    needs_key: boolean;
    base_url?: string;
}

/** One model a provider offers (GET /api/settings/provider-models/{provider}). */
export interface ProviderModel {
    id: string;
    name: string;
    context: number | null;
    /** USD per 1M tokens, when the provider publishes it (OpenRouter). */
    price: { input: number; output: number } | null;
}

export interface SettingsView {
    settings: SettingField[];
    secrets: SecretStatus[];
    issues: ConfigIssue[];
    models: RoutedModel[];
    roles: Record<RoleName, RoleChain>;
    providers: Record<ProviderName, ProviderState>;
    workspace: { path: string; exists: boolean };
    ready: boolean;
    onboarding: { completed: boolean; completed_at: string | null };
}

/** Setting name -> new value; null goes back to the environment or default. */
export type SettingChanges = Record<string, string | null>;

export interface SaveOutcome {
    ok: boolean;
    message?: string;
    errors: Record<string, string>;
}

function failure(err: unknown): SaveOutcome {
    if (err instanceof ApiError) {
        return { ok: false, message: err.message, errors: err.errors };
    }
    return { ok: false, message: err instanceof Error ? err.message : String(err), errors: {} };
}

export function useSettings() {
    const [view, setView] = useState<SettingsView | null>(null);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        try {
            setView(await getJson<SettingsView>("/api/settings"));
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        }
    }, []);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    const save = useCallback(async (values: SettingChanges): Promise<SaveOutcome> => {
        try {
            setView(await putJson<SettingsView>("/api/settings", { values }));
            return { ok: true, errors: {} };
        } catch (err) {
            return failure(err);
        }
    }, []);

    const finishOnboarding = useCallback(async (): Promise<SaveOutcome> => {
        try {
            setView(await postJson<SettingsView>("/api/settings/onboarding", {}));
            return { ok: true, errors: {} };
        } catch (err) {
            return failure(err);
        }
    }, []);

    return { view, error, refresh, save, finishOnboarding };
}

/** Build AEHUB_MODEL_PRICES from the current JSON plus edited rows. */
export function mergePrices(
    current: string,
    rows: Record<string, { input: string; output: string }>,
): string {
    let table: Record<string, { input: number; output: number }> = {};

    try {
        const parsed = current.trim() ? JSON.parse(current) : {};
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
            table = parsed;
        }
    } catch {
        // Invalid JSON is replaced by the rows; the backend validates anyway.
    }

    for (const [model, price] of Object.entries(rows)) {
        if (price.input.trim() === "" && price.output.trim() === "") {
            continue;
        }
        table[model] = { input: Number(price.input), output: Number(price.output) };
    }

    return JSON.stringify(table);
}

/**
 * The models each provider offers (F4), loaded once per page: a list, or
 * the reason it is missing (no key, server off). Suggestions only.
 */
export function useProviderModels(providers: ProviderName[]) {
    const [models, setModels] = useState<Partial<Record<ProviderName, ProviderModel[]>>>({});
    const [missing, setMissing] = useState<Partial<Record<ProviderName, string>>>({});
    const wanted = providers.join(",");

    useEffect(() => {
        let active = true;
        for (const provider of wanted.split(",").filter(Boolean) as ProviderName[]) {
            getJson<{ models: ProviderModel[] }>(`/api/settings/provider-models/${provider}`)
                .then((result) => active && setModels((current) => ({ ...current, [provider]: result.models })))
                .catch(
                    (err: unknown) =>
                        active &&
                        setMissing((current) => ({
                            ...current,
                            [provider]: err instanceof Error ? err.message : String(err),
                        })),
                );
        }
        return () => {
            active = false;
        };
    }, [wanted]);

    return { models, missing };
}
