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

type SessionState = "checking" | "signed-in" | "signed-out" | "unreachable";

export function LoginForm({ onSignedIn }: { onSignedIn: () => void }) {
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
            onSignedIn();
        } catch (err) {
            if (err instanceof ApiError && err.status === 401) {
                setError("Wrong access key.");
            } else if (err instanceof ApiError && err.status === 429) {
                setError("Too many attempts: wait a few minutes.");
            } else {
                setError(err instanceof Error ? err.message : String(err));
            }
        } finally {
            setBusy(false);
        }
    };

    return (
        <form onSubmit={submit} className="max-w-sm mx-auto mt-24 space-y-4" aria-label="Sign in">
            <h1 className="text-2xl font-bold text-orange-500">ÆHub Control Plane</h1>
            <label className="block text-sm text-gray-300" htmlFor="access-key">
                Access key
            </label>
            <input
                id="access-key"
                type="password"
                autoComplete="current-password"
                value={key}
                onChange={(event) => setKey(event.target.value)}
                className="w-full rounded bg-gray-900 border border-gray-700 px-3 py-2 text-white"
                required
            />
            {error && (
                <p role="alert" className="text-red-400 text-sm">
                    {error}
                </p>
            )}
            <button
                type="submit"
                disabled={busy || key.length === 0}
                className="w-full bg-orange-600 hover:bg-orange-500 disabled:opacity-50 rounded px-4 py-2 font-semibold"
            >
                {busy ? "Signing in..." : "Sign in"}
            </button>
        </form>
    );
}

export default function AuthGate({ children }: { children: React.ReactNode }) {
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
        return <p className="p-8 text-gray-400">Checking session...</p>;
    }

    if (state === "unreachable") {
        return (
            <div className="p-8">
                <p className="text-red-400 mb-4">The backend is not reachable.</p>
                <button onClick={check} className="bg-gray-700 hover:bg-gray-600 px-4 py-1 rounded">
                    Retry
                </button>
            </div>
        );
    }

    if (state === "signed-out") {
        return <LoginForm onSignedIn={check} />;
    }

    return <>{children}</>;
}
