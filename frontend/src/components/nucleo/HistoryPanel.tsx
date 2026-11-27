/**
 * @file frontend/src/components/nucleo/HistoryPanel.tsx
 * @description The Nucleo's past conversations (N6): search them, open one
 * to go on with it, or start a new one.
 *
 * A conversation is a session of the engine: its recent turns and summary
 * are what the agents remember of it. Opening one shows its turns in the
 * conversation pane, and the next command goes on in it. While commands are
 * still running the conversation cannot change: their answers belong to the
 * one they were sent in.
 */
"use client";

import React, { useEffect, useState } from "react";

import { getJson } from "@/lib/api/client";
import { catalog, useLanguage } from "@/lib/i18n";

import styles from "./nucleo.module.css";

export interface ConversationSummary {
    id: string;
    title: string;
    turns: number;
    started_at: string | null;
    updated_at: string | null;
    match: string | null;
}

export interface ConversationTurn {
    run_id: string;
    task: string;
    answer: string;
    status: string;
    channel: "voice" | "text";
    created_at: string | null;
}

const TEXT = catalog({
    en: {
        search: "Search the conversations",
        placeholder: "search commands and answers…",
        fresh: "New conversation",
        busy: "Wait for the running commands to end.",
        none: "No conversation yet.",
        noMatch: "No conversation matches.",
        loading: "Loading…",
        failed: "Not loaded:",
        turns: (count: number) => (count === 1 ? "1 command" : `${count} commands`),
        current: "current",
        matched: "found in:",
        list: "Past conversations",
    },
    it: {
        search: "Cerca nelle conversazioni",
        placeholder: "cerca nei comandi e nelle risposte…",
        fresh: "Nuova conversazione",
        busy: "Aspetta che finiscano i comandi in corso.",
        none: "Ancora nessuna conversazione.",
        noMatch: "Nessuna conversazione corrisponde.",
        loading: "Caricamento…",
        failed: "Non caricate:",
        turns: (count: number) => (count === 1 ? "1 comando" : `${count} comandi`),
        current: "attuale",
        matched: "trovato in:",
        list: "Conversazioni passate",
    },
});

/** The path of a conversation: "_" is the principal's own session, whose id is "". */
export function conversationPath(id: string): string {
    return `/api/conversations/${id ? encodeURIComponent(id) : "_"}`;
}

export default function HistoryPanel({
    current,
    busy,
    onOpen,
    onNew,
}: {
    /** The id of the conversation the next command goes on in. */
    current: string;
    /** Commands are running: the conversation cannot change now. */
    busy: boolean;
    onOpen: (id: string) => void;
    onNew: () => void;
}) {
    const lang = useLanguage();
    const t = TEXT[lang];
    const [query, setQuery] = useState("");
    const [found, setFound] = useState<ConversationSummary[] | null>(null);
    const [error, setError] = useState("");

    // A short pause after typing, so a search is not sent at every key.
    useEffect(() => {
        let gone = false;
        const timer = setTimeout(
            async () => {
                try {
                    const params = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
                    const view = await getJson<{ conversations: ConversationSummary[] }>(
                        `/api/conversations${params}`
                    );
                    if (!gone) {
                        setFound(view.conversations);
                        setError("");
                    }
                } catch (failure) {
                    if (!gone) {
                        setError(failure instanceof Error ? failure.message : String(failure));
                    }
                }
            },
            query ? 250 : 0
        );
        return () => {
            gone = true;
            clearTimeout(timer);
        };
    }, [query]);

    return (
        <div className={styles.history}>
            <div className={styles.historyBar}>
                <input
                    type="search"
                    aria-label={t.search}
                    placeholder={t.placeholder}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                />
                <button
                    type="button"
                    onClick={onNew}
                    disabled={busy}
                    title={busy ? t.busy : undefined}
                >
                    {t.fresh}
                </button>
            </div>
            {busy && (
                <p className={styles.empty} role="status">
                    {t.busy}
                </p>
            )}
            {error && (
                <p className={styles.empty} role="alert">
                    {t.failed} {error}
                </p>
            )}
            <ul className={styles.historyList} aria-label={t.list}>
                {found === null && !error ? (
                    <li className={styles.empty}>{t.loading}</li>
                ) : found && found.length === 0 ? (
                    <li className={styles.empty}>{query.trim() ? t.noMatch : t.none}</li>
                ) : (
                    (found ?? []).map((item) => (
                        <li key={item.id || "_"}>
                            <button
                                type="button"
                                className={styles.historyItem}
                                aria-current={item.id === current ? "true" : undefined}
                                disabled={busy}
                                onClick={() => onOpen(item.id)}
                            >
                                <span className={styles.historyTitle}>{item.title}</span>
                                <span className={styles.who}>
                                    {t.turns(item.turns)}
                                    {item.updated_at
                                        ? ` · ${new Date(item.updated_at).toLocaleString(lang)}`
                                        : ""}
                                    {item.id === current ? ` · ${t.current}` : ""}
                                </span>
                                {item.match && item.match !== item.title && (
                                    <span className={styles.historyMatch}>
                                        {t.matched} {item.match}
                                    </span>
                                )}
                            </button>
                        </li>
                    ))
                )}
            </ul>
        </div>
    );
}
