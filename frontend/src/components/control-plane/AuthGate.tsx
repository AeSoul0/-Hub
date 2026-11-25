/**
 * @file frontend/src/components/control-plane/AuthGate.tsx
 * @description Session check and login form for the Control Plane (M11).
 *
 * GET /api/auth/verify tells whether the HttpOnly session cookie is valid.
 * Without a session the pages would only show 401 errors, so the gate asks
 * for the access key (AEHUB_SECRET_KEY) and logs in with POST /api/auth/login.
 * The token never reaches page scripts: it lives in the cookie.
 */
"use client";

import React, { useCallback, useEffect, useState } from "react";

import { ApiError, getJson, postJson } from "@/lib/api/client";
import { catalog, refreshInterface, useText } from "@/lib/i18n";

import styles from "./control.module.css";

const TEXT = catalog({
    en: {
        wrongKey: "Wrong access key.",
        tooMany: "Too many attempts: wait a few minutes.",
        signIn: "Sign in",
        accessKey: "Access key",
        signingIn: "Signing in…",
        checking: "Checking the session…",
        unreachable: "The backend is not reachable.",
        retry: "Retry",
    },
    it: {
        wrongKey: "Chiave di accesso sbagliata.",
        tooMany: "Troppi tentativi: aspetta qualche minuto.",
        signIn: "Entra",
        accessKey: "Chiave di accesso",
        signingIn: "Accesso in corso…",
        checking: "Controllo la sessione…",
        unreachable: "Il backend non risponde.",
        retry: "Riprova",
    },
});

type SessionState = "checking" | "signed-in" | "signed-out" | "unreachable";

export function LoginForm({ onSignedIn }: { onSignedIn: () => void }) {
    const t = useText(TEXT);
    const [key, setKey] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const submit = async (event: React.FormEvent) => {
        event.preventDefault();
        setBusy(true);
        setError(null);

        try {
            await postJson("/api/auth/login", { key });
            setKey("");
            refreshInterface();
            onSignedIn();
        } catch (err) {
            if (err instanceof ApiError && err.status === 401) {
                setError(t.wrongKey);
            } else if (err instanceof ApiError && err.status === 429) {
                setError(t.tooMany);
            } else {
                setError(err instanceof Error ? err.message : String(err));
            }
        } finally {
            setBusy(false);
        }
    };

    return (
        <main className={styles.gate}>
            <form
                onSubmit={submit}
                className={`surface rise ${styles.gateCard}`}
                aria-label={t.signIn}
            >
                <h1 className={styles.mark}>
                    ÆHUB<small>CONTROL PLANE</small>
                </h1>
                <label className={styles.field} htmlFor="access-key">
                    {t.accessKey}
                    <input
                        id="access-key"
                        type="password"
                        autoComplete="current-password"
                        value={key}
                        onChange={(event) => setKey(event.target.value)}
                        required
                    />
                </label>
                {error && (
                    <p role="alert" className={styles.error}>
                        {error}
                    </p>
                )}
                <button
                    type="submit"
                    disabled={busy || key.length === 0}
                    className={`${styles.btn} ${styles.gateButton}`}
                >
                    {busy ? t.signingIn : t.signIn}
                </button>
            </form>
        </main>
    );
}

export default function AuthGate({ children }: { children: React.ReactNode }) {
    const t = useText(TEXT);
    const [state, setState] = useState<SessionState>("checking");

    const check = useCallback(async () => {
        try {
            await getJson("/api/auth/verify");
            setState("signed-in");
        } catch (err) {
            setState(err instanceof ApiError && err.status === 401 ? "signed-out" : "unreachable");
        }
    }, []);

    useEffect(() => {
        const first = setTimeout(check, 0);
        return () => clearTimeout(first);
    }, [check]);

    if (state === "checking") {
        return (
            <main className={styles.gate}>
                <p className={styles.muted} role="status">
                    {t.checking}
                </p>
            </main>
        );
    }

    if (state === "unreachable") {
        return (
            <main className={styles.gate}>
                <div className={`surface rise ${styles.gateCard}`}>
                    <p role="alert" className={styles.error}>
                        {t.unreachable}
                    </p>
                    <button onClick={check} className={styles.btn}>
                        {t.retry}
                    </button>
                </div>
            </main>
        );
    }

    if (state === "signed-out") {
        return <LoginForm onSignedIn={check} />;
    }

    return <>{children}</>;
}
