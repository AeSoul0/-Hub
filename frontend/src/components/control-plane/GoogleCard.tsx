/**
 * @file frontend/src/components/control-plane/GoogleCard.tsx
 * @description The owner's Google account on STRUMENTI (N4, ADR-046): how
 * to create the OAuth client, Connect, the connected account, Disconnect.
 *
 * Connect asks the backend for Google's consent page and goes there; Google
 * comes back to the backend, which sends the browser here with ?google=…
 * Where no keyring keeps the token (Docker, a codespace) the page shows it
 * once, to be saved as the secret GOOGLE_REFRESH_TOKEN.
 */
"use client";

import React, { useCallback, useEffect, useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import { deleteJson, getJson, postJson } from "@/lib/api/client";
import { catalog, useLanguage } from "@/lib/i18n";

export interface GoogleStatus {
    client_configured: boolean;
    connected: boolean;
    account: string | null;
    token_source: "keyring" | "environment" | "memory" | null;
    problem: string | null;
    redirect_uri: string;
    scopes: string[];
    token_to_save: string | null;
}

const TEXT = catalog({
    en: {
        title: "Google",
        help: "Your Google Calendar and Gmail for the agents: reading events and mail is low risk, creating an event medium, sending an email always waits for your yes.",
        setupTitle: "To connect, once:",
        steps: [
            "In Google Cloud Console create a project and enable the Google Calendar API and the Gmail API.",
            "OAuth consent screen: External, add your own address as a test user.",
            "Credentials → Create OAuth client ID → Web application, with this authorized redirect URI:",
            "Save the client's id and secret as GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET (codespace secrets, or python scripts/aehub.py setup), then restart ÆHub.",
        ],
        testing:
            "While the app is in Testing at Google, Google ends the connection after 7 days: connect again, or publish the app.",
        copy: "Copy",
        copied: "Copied",
        connect: "Connect Google",
        reconnect: "Connect again",
        disconnect: "Disconnect",
        confirm: "Click again to disconnect",
        connected: (account: string) => `Connected: ${account}`,
        connectedNoName: "Connected",
        source: {
            keyring: "token in the keyring",
            environment: "token from GOOGLE_REFRESH_TOKEN",
            memory: "token kept until ÆHub restarts",
        },
        saveTitle: "Keep the connection after a restart",
        saveHelp:
            "There is no keyring here: save this value as the secret GOOGLE_REFRESH_TOKEN (codespace secret, or python scripts/aehub.py setup). It is shown only now.",
        removeSecret: (name: string) =>
            `Disconnected. Remove the secret ${name} too, or it comes back at the next start.`,
        disconnected: "Disconnected.",
        back: {
            connected: "Google connected.",
            refused: "Google: the connection was not allowed.",
            missing: "Google connected without every permission: connect again and tick every box.",
        },
        failed: "Not done:",
    },
    it: {
        title: "Google",
        help: "Il tuo Google Calendar e Gmail per gli agenti: leggere eventi e posta è a basso rischio, creare un evento medio, mandare una email aspetta sempre il tuo sì.",
        setupTitle: "Per collegarlo, una volta:",
        steps: [
            "In Google Cloud Console crea un progetto e attiva Google Calendar API e Gmail API.",
            "Schermata di consenso OAuth: Esterno, aggiungi il tuo indirizzo come utente di test.",
            "Credenziali → Crea ID client OAuth → Applicazione web, con questo URI di reindirizzamento autorizzato:",
            "Salva id e segreto del client come GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET (secret del Codespace, o python scripts/aehub.py setup), poi riavvia ÆHub.",
        ],
        testing:
            "Finché l'app è «In test» su Google, Google chiude il collegamento dopo 7 giorni: ricollegalo, o pubblica l'app.",
        copy: "Copia",
        copied: "Copiato",
        connect: "Collega Google",
        reconnect: "Ricollega",
        disconnect: "Scollega",
        confirm: "Clicca ancora per scollegare",
        connected: (account: string) => `Collegato: ${account}`,
        connectedNoName: "Collegato",
        source: {
            keyring: "token nel portachiavi",
            environment: "token da GOOGLE_REFRESH_TOKEN",
            memory: "token tenuto finché ÆHub non si riavvia",
        },
        saveTitle: "Tieni il collegamento dopo un riavvio",
        saveHelp:
            "Qui non c'è un portachiavi: salva questo valore come secret GOOGLE_REFRESH_TOKEN (secret del Codespace, o python scripts/aehub.py setup). Si vede solo ora.",
        removeSecret: (name: string) =>
            `Scollegato. Togli anche il secret ${name}, o torna al prossimo avvio.`,
        disconnected: "Scollegato.",
        back: {
            connected: "Google collegato.",
            refused: "Google: il collegamento non è stato permesso.",
            missing:
                "Google collegato senza tutti i permessi: ricollegalo e spunta tutte le caselle.",
        },
        failed: "Non fatto:",
    },
});

function errorText(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
}

export default function GoogleCard() {
    const lang = useLanguage();
    const t = TEXT[lang];
    const [status, setStatus] = useState<GoogleStatus | null>(null);
    // The token to save, kept on screen after the status that brought it.
    const [toSave, setToSave] = useState<string | null>(null);
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const [confirm, setConfirm] = useState(false);
    const [copied, setCopied] = useState("");

    const load = useCallback(async () => {
        try {
            const next = await getJson<GoogleStatus>("/api/google");
            setStatus(next);
            if (next.token_to_save) {
                setToSave(next.token_to_save);
            }
        } catch (error) {
            setNote(`${TEXT[lang].failed} ${errorText(error)}`);
        }
    }, [lang]);

    useEffect(() => {
        const first = setTimeout(() => {
            // Back from Google: ?google=connected | refused | missing-…
            const back = new URLSearchParams(window.location.search).get("google") ?? "";
            if (back) {
                const key = back.startsWith("missing")
                    ? "missing"
                    : back === "connected"
                      ? "connected"
                      : "refused";
                setNote(TEXT[lang].back[key]);
                const url = new URL(window.location.href);
                url.searchParams.delete("google");
                window.history.replaceState(null, "", url.toString());
            }
            void load();
        }, 0);
        return () => clearTimeout(first);
    }, [load, lang]);

    const connect = async () => {
        setBusy(true);
        try {
            const { url } = await postJson<{ url: string }>("/api/google/connect", {
                origin: window.location.origin,
            });
            window.location.assign(url);
        } catch (error) {
            setNote(`${t.failed} ${errorText(error)}`);
            setBusy(false);
        }
    };

    const disconnect = async () => {
        if (!confirm) {
            setConfirm(true);
            return;
        }
        setBusy(true);
        try {
            const done = await deleteJson<{ remove_secret: string | null }>("/api/google");
            setNote(done.remove_secret ? t.removeSecret(done.remove_secret) : t.disconnected);
            setToSave(null);
        } catch (error) {
            setNote(`${t.failed} ${errorText(error)}`);
        } finally {
            setBusy(false);
            setConfirm(false);
            void load();
        }
    };

    const copy = async (what: string, value: string) => {
        try {
            await navigator.clipboard.writeText(value);
            setCopied(what);
        } catch {
            setCopied("");
        }
    };

    return (
        <section className={styles.card} aria-label={t.title}>
            <h2 className={styles.h2}>{t.title}</h2>
            <p className={styles.help}>{t.help}</p>
            {status && !status.client_configured && (
                <div className={styles.stack}>
                    <p className={styles.help}>{t.setupTitle}</p>
                    <ol className={styles.help}>
                        {t.steps.map((step, index) => (
                            <li key={index}>
                                {step}
                                {index === 2 && (
                                    <span className={styles.row}>
                                        <code className={styles.mono}>{status.redirect_uri}</code>
                                        <button
                                            type="button"
                                            className={styles.linkBtn}
                                            onClick={() => void copy("uri", status.redirect_uri)}
                                        >
                                            {copied === "uri" ? t.copied : t.copy}
                                        </button>
                                    </span>
                                )}
                            </li>
                        ))}
                    </ol>
                    <p className={styles.help}>{t.testing}</p>
                </div>
            )}
            {status?.client_configured && !status.connected && (
                <div className={styles.row}>
                    <button
                        type="button"
                        className={`${styles.btn} ${styles.go}`}
                        disabled={busy}
                        onClick={() => void connect()}
                    >
                        {t.connect}
                    </button>
                    <span className={styles.help}>
                        <code className={styles.mono}>{status.redirect_uri}</code>
                    </span>
                </div>
            )}
            {status?.connected && (
                <div className={styles.stack}>
                    <p className={styles.muted}>
                        {status.account ? t.connected(status.account) : t.connectedNoName}
                        {status.token_source && ` · ${t.source[status.token_source]}`}
                    </p>
                    {status.problem && (
                        <p className={styles.warn} role="alert">
                            {status.problem}
                        </p>
                    )}
                    <div className={styles.row}>
                        {status.problem && (
                            <button
                                type="button"
                                className={`${styles.btn} ${styles.go}`}
                                disabled={busy}
                                onClick={() => void connect()}
                            >
                                {t.reconnect}
                            </button>
                        )}
                        <button
                            type="button"
                            className={styles.btn}
                            disabled={busy}
                            onClick={() => void disconnect()}
                        >
                            {confirm ? t.confirm : t.disconnect}
                        </button>
                    </div>
                    <p className={styles.help}>{t.testing}</p>
                </div>
            )}
            {toSave && (
                <div className={styles.stack}>
                    <h3 className={styles.h2}>{t.saveTitle}</h3>
                    <p className={styles.help}>{t.saveHelp}</p>
                    <div className={styles.row}>
                        <input
                            className={styles.input}
                            readOnly
                            value={toSave}
                            aria-label="GOOGLE_REFRESH_TOKEN"
                            spellCheck={false}
                        />
                        <button
                            type="button"
                            className={styles.linkBtn}
                            onClick={() => void copy("token", toSave)}
                        >
                            {copied === "token" ? t.copied : t.copy}
                        </button>
                    </div>
                </div>
            )}
            {note && (
                <p className={styles.help} role="status">
                    {note}
                </p>
            )}
        </section>
    );
}
