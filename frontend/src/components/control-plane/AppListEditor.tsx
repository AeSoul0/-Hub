/**
 * @file frontend/src/components/control-plane/AppListEditor.tsx
 * @description The apps ÆHub may open (AEHUB_APPS, V1, ADR-035): one row per app, saved as the JSON the backend reads.
 *
 * A row is the name the user says, the program (a path, a command, a link or
 * "spotify:") and optional arguments. Arguments are split on spaces; a part
 * with spaces goes in double quotes. The backend validates the result again.
 */
"use client";

import React, { useState } from "react";

import { catalog, useText } from "@/lib/i18n";

import styles from "./control.module.css";

const TEXT = catalog({
    en: {
        name: "Name you say",
        program: "Program, path or link",
        args: "Arguments (optional)",
        remove: "Remove",
        add: "Add an app",
        save: "Save apps",
        empty: "No app yet: ÆHub opens only the apps listed here.",
        list: "Apps ÆHub may open",
        missing: "Every row needs a name and a program.",
        twice: "Two apps have the same name.",
    },
    it: {
        name: "Nome che dici",
        program: "Programma, percorso o link",
        args: "Argomenti (facoltativi)",
        remove: "Togli",
        add: "Aggiungi un'app",
        save: "Salva le app",
        empty: "Nessuna app: ÆHub apre solo le app elencate qui.",
        list: "App che ÆHub può aprire",
        missing: "Ogni riga ha bisogno di un nome e di un programma.",
        twice: "Due app hanno lo stesso nome.",
    },
});

export interface AppRow {
    name: string;
    program: string;
    args: string;
}

/** Split arguments on spaces, keeping "double quoted parts" whole. */
export function splitArgs(text: string): string[] {
    const parts = text.match(/"[^"]*"|\S+/g) ?? [];
    return parts.map((part) =>
        part.startsWith('"') && part.endsWith('"') && part.length >= 2 ? part.slice(1, -1) : part
    );
}

function joinArgs(args: string[]): string {
    return args.map((arg) => (/\s/.test(arg) || arg === "" ? `"${arg}"` : arg)).join(" ");
}

/** The rows of a stored AEHUB_APPS value; an invalid value gives no rows. */
export function appRows(json: string | undefined): AppRow[] {
    if (!json?.trim()) {
        return [];
    }
    try {
        const parsed: unknown = JSON.parse(json);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
            return [];
        }
        return Object.entries(parsed as Record<string, unknown>).map(([name, target]) => {
            if (Array.isArray(target)) {
                const [program = "", ...args] = target.map(String);
                return { name, program, args: joinArgs(args) };
            }
            return { name, program: String(target ?? ""), args: "" };
        });
    } catch {
        return [];
    }
}

/** The AEHUB_APPS value for these rows: a plain string without arguments, a list with them. */
export function appsJson(rows: AppRow[]): string {
    if (rows.length === 0) {
        return "";
    }
    const entries = rows.map((row) => {
        const args = splitArgs(row.args);
        const program = row.program.trim();
        return [row.name.trim(), args.length ? [program, ...args] : program] as const;
    });
    return JSON.stringify(Object.fromEntries(entries));
}

export default function AppListEditor({
    value,
    busy,
    error,
    onSave,
}: {
    value: string | undefined;
    busy: boolean;
    error?: string;
    onSave: (json: string) => void;
}) {
    const t = useText(TEXT);
    const [rows, setRows] = useState<AppRow[]>(() => appRows(value));
    const [problem, setProblem] = useState<string | null>(null);

    const change = (index: number, key: keyof AppRow, text: string) =>
        setRows((current) =>
            current.map((row, at) => (at === index ? { ...row, [key]: text } : row))
        );

    const save = (event: React.FormEvent) => {
        event.preventDefault();
        if (rows.some((row) => !row.name.trim() || !row.program.trim())) {
            setProblem(t.missing);
            return;
        }
        const names = rows.map((row) => row.name.trim().toLowerCase());
        if (new Set(names).size !== names.length) {
            setProblem(t.twice);
            return;
        }
        setProblem(null);
        onSave(appsJson(rows));
    };

    return (
        <form onSubmit={save} className={styles.stack} aria-label={t.list}>
            {rows.length === 0 && <p className={styles.muted}>{t.empty}</p>}
            {rows.map((row, index) => (
                <div
                    key={index}
                    className={styles.filters}
                    role="group"
                    aria-label={row.name || t.add}
                >
                    <label className={styles.field}>
                        {t.name}
                        <input
                            value={row.name}
                            onChange={(event) => change(index, "name", event.target.value)}
                            maxLength={40}
                        />
                    </label>
                    <label className={`${styles.field} ${styles.grow}`}>
                        {t.program}
                        <input
                            value={row.program}
                            onChange={(event) => change(index, "program", event.target.value)}
                        />
                    </label>
                    <label className={styles.field}>
                        {t.args}
                        <input
                            value={row.args}
                            onChange={(event) => change(index, "args", event.target.value)}
                        />
                    </label>
                    <button
                        type="button"
                        className={`${styles.btn} ${styles.danger}`}
                        onClick={() =>
                            setRows((current) => current.filter((_, at) => at !== index))
                        }
                    >
                        {t.remove}
                    </button>
                </div>
            ))}
            {(problem || error) && (
                <p role="alert" className={styles.error}>
                    {problem || error}
                </p>
            )}
            <div className={styles.row}>
                <button
                    type="button"
                    className={styles.btn}
                    onClick={() =>
                        setRows((current) => [...current, { name: "", program: "", args: "" }])
                    }
                >
                    {t.add}
                </button>
                <button type="submit" className={`${styles.btn} ${styles.ok}`} disabled={busy}>
                    {t.save}
                </button>
            </div>
        </form>
    );
}
