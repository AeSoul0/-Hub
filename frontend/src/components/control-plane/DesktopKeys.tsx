/**
 * @file frontend/src/components/control-plane/DesktopKeys.tsx
 * @description Provider keys typed in the desktop app (M14, ADR-020).
 *
 * The desktop app has no terminal for the launcher, so keys are sent once
 * to PUT /api/desktop/secrets, which writes them to the OS keyring. They are
 * never read back: the list above only says whether each one is set.
 */
"use client";

import React, { useEffect, useState } from "react";

import { ApiError, getJson, putJson } from "@/lib/api/client";

const KEYS = [
    { name: "OPENAI_API_KEY", label: "OpenAI" },
    { name: "OPENROUTER_API_KEY", label: "OpenRouter" },
    { name: "AEHUB_MQTT_PASSWORD", label: "MQTT broker (home, optional)" },
] as const;

/** Whether this frontend runs inside the desktop app. */
export function useDesktopMode(): boolean {
    const [desktop, setDesktop] = useState(false);

    useEffect(() => {
        let active = true;
        getJson<{ desktop: boolean }>("/api/desktop")
            .then((status) => active && setDesktop(Boolean(status.desktop)))
            .catch(() => active && setDesktop(false));
        return () => {
            active = false;
        };
    }, []);

    return desktop;
}

export default function DesktopKeys({ onSaved }: { onSaved: () => void }) {
    const [values, setValues] = useState<Record<string, string>>({});
    const [message, setMessage] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const submit = async (event: React.FormEvent) => {
        event.preventDefault();
        const changes = Object.fromEntries(
            Object.entries(values).filter(([, value]) => value.trim() !== ""),
        );
        if (Object.keys(changes).length === 0) {
            return;
        }
        setBusy(true);
        try {
            await putJson("/api/desktop/secrets", changes);
            setValues({});
            setMessage("Saved in the OS keyring.");
            onSaved();
        } catch (err) {
            setMessage(err instanceof ApiError ? err.message : String(err));
        } finally {
            setBusy(false);
        }
    };

    return (
        <form onSubmit={submit} className="mt-4 space-y-2" aria-label="Add keys">
            {KEYS.map((key) => (
                <label key={key.name} className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="w-48">{key.label}</span>
                    <input
                        type="password"
                        autoComplete="off"
                        name={key.name}
                        value={values[key.name] ?? ""}
                        onChange={(event) => setValues({ ...values, [key.name]: event.target.value })}
                        className="bg-gray-900 border border-gray-700 rounded px-2 py-1 font-mono"
                    />
                </label>
            ))}
            <button type="submit" disabled={busy} className="bg-orange-600 hover:bg-orange-500 rounded px-4 py-1">
                Save keys
            </button>
            {message && <p className="text-sm text-gray-300">{message}</p>}
        </form>
    );
}
