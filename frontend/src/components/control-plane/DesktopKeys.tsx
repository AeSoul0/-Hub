/**
 * @file frontend/src/components/control-plane/DesktopKeys.tsx
 * @description Keys typed in the desktop app (M14, ADR-020; every key the
 * backend knows since F4).
 *
 * The desktop app has no terminal for the launcher, so keys are sent once
 * to PUT /api/desktop/secrets, which writes them to the OS keyring. They are
 * never read back: the list only says whether each one is set.
 */
"use client";

import React, { useEffect, useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import { ApiError, getJson, putJson } from "@/lib/api/client";
import type { SecretStatus } from "@/lib/api/settings";
import { catalog, useLanguage } from "@/lib/i18n";
import { SECRET_TEXT } from "@/lib/nucleo/models";

const TEXT = catalog({
    en: { saved: "Saved in the system keyring.", form: "Add keys", replace: "replace", save: "Save the keys" },
    it: {
        saved: "Salvate nel portachiavi del sistema.",
        form: "Aggiungi chiavi",
        replace: "sostituisci",
        save: "Salva le chiavi",
    },
});

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

export default function DesktopKeys({ secrets, onSaved }: { secrets: SecretStatus[]; onSaved: () => void }) {
    const lang = useLanguage();
    const t = TEXT[lang];
    const [values, setValues] = useState<Record<string, string>>({});
    const [message, setMessage] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const submit = async (event: React.FormEvent) => {
        event.preventDefault();
        const changes = Object.fromEntries(
            Object.entries(values)
                .map(([name, value]) => [name, value.trim()])
                .filter(([, value]) => value !== ""),
        );
        if (Object.keys(changes).length === 0) {
            return;
        }
        setBusy(true);
        try {
            await putJson("/api/desktop/secrets", changes);
            setValues({});
            setMessage(t.saved);
            onSaved();
        } catch (err) {
            setMessage(err instanceof ApiError ? err.message : String(err));
        } finally {
            setBusy(false);
        }
    };

    return (
        <form onSubmit={submit} className={styles.filters} aria-label={t.form}>
            {secrets.map((secret) => (
                <label key={secret.name} className={styles.field}>
                    {SECRET_TEXT[lang][secret.name]?.label ?? secret.label}
                    <input
                        type="password"
                        autoComplete="off"
                        name={secret.name}
                        placeholder={secret.configured ? t.replace : ""}
                        value={values[secret.name] ?? ""}
                        onChange={(event) => setValues({ ...values, [secret.name]: event.target.value })}
                    />
                </label>
            ))}
            <button type="submit" disabled={busy} className={`${styles.btn} ${styles.go}`}>
                {t.save}
            </button>
            {message && (
                <p className={styles.muted} role="status">
                    {message}
                </p>
            )}
        </form>
    );
}
