/**
 * @file frontend/src/app/control-plane/documents/page.tsx
 * @description Documenti (F6, ADR-027): the user's documents in the working
 * folder that the agent searches and cites.
 *
 * - The folder, the totals and a sync now (POST /api/documents/sync).
 * - Upload a file into the folder (POST /api/documents/upload, admin),
 *   indexed at once; an existing name is replaced only when asked.
 * - The size limit (AEHUB_DOCUMENTS_MAX_FILE_MB, PUT /api/settings).
 * - Search the index as the agent does (GET /api/documents/search) and
 *   read each passage with its citation.
 * - Every indexed file, with its pieces or the reason it is not searched.
 *
 * Documents are third-party content: the agent cites them as
 * [doc: path#location] and never follows them as instructions.
 */
"use client";

import React, { useCallback, useEffect, useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import { getJson, postForm, postJson } from "@/lib/api/client";
import {
    formatSize,
    locatorLabel,
    type DocumentHit,
    type DocumentsView,
    type SyncReport,
} from "@/lib/api/memory";
import { useSettings } from "@/lib/api/settings";
import { errorText } from "@/lib/nucleo/memory";

function message(err: unknown): string {
    return errorText(err instanceof Error ? err.message : String(err));
}

function syncSummary(report: SyncReport): string {
    if (!report.root_exists) {
        return "La cartella di lavoro non esiste.";
    }
    const parts = [
        report.added.length && `${report.added.length} aggiunti`,
        report.updated.length && `${report.updated.length} aggiornati`,
        report.removed.length && `${report.removed.length} tolti`,
        report.failed.length && `${report.failed.length} con errori`,
        report.pending && `${report.pending} in attesa`,
    ].filter(Boolean);
    return parts.length ? `Sincronizzato: ${parts.join(", ")}.` : "Sincronizzato: niente di nuovo.";
}

function date(value: string | null): string {
    if (!value) {
        return "-";
    }
    const parsed = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
    return Number.isNaN(parsed.getTime())
        ? value
        : parsed.toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function DocumentsPage() {
    const { view: settings, save } = useSettings();
    const [view, setView] = useState<DocumentsView | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [note, setNote] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [file, setFile] = useState<File | null>(null);
    const [replace, setReplace] = useState(false);
    const [uploadError, setUploadError] = useState<string | null>(null);
    const [maxMb, setMaxMb] = useState<string | null>(null);
    const [query, setQuery] = useState("");
    const [hits, setHits] = useState<DocumentHit[] | null>(null);
    const [searchError, setSearchError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        try {
            setView(await getJson<DocumentsView>("/api/documents"));
            setError(null);
        } catch (err) {
            setError(message(err));
        }
    }, []);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    const savedMb = settings?.settings.find((field) => field.name === "AEHUB_DOCUMENTS_MAX_FILE_MB")?.value ?? "";
    useEffect(() => {
        if (settings) {
            const reset = setTimeout(() => setMaxMb(savedMb || "5"), 0);
            return () => clearTimeout(reset);
        }
    }, [settings, savedMb]);

    const sync = async () => {
        setBusy(true);
        setNote(null);
        try {
            setNote(syncSummary(await postJson<SyncReport>("/api/documents/sync", {})));
            await refresh();
        } catch (err) {
            setNote(message(err));
        } finally {
            setBusy(false);
        }
    };

    const upload = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!file) {
            return;
        }
        setBusy(true);
        setUploadError(null);
        setNote(null);
        try {
            const form = new FormData();
            form.append("file", file, file.name);
            form.append("replace", replace ? "true" : "false");
            const result = await postForm<{ path: string; sync: SyncReport }>("/api/documents/upload", form);
            setNote(`${result.path} caricato. ${syncSummary(result.sync)}`);
            setFile(null);
            setReplace(false);
            (event.target as HTMLFormElement).reset();
            await refresh();
        } catch (err) {
            setUploadError(message(err));
        } finally {
            setBusy(false);
        }
    };

    const saveMax = async () => {
        if (maxMb === null) {
            return;
        }
        setBusy(true);
        const outcome = await save({ AEHUB_DOCUMENTS_MAX_FILE_MB: maxMb.trim() });
        setBusy(false);
        setNote(
            outcome.ok
                ? "Dimensione massima salvata: vale dalla prossima sincronizzazione."
                : `${outcome.message ?? "Non salvato."} ${Object.values(outcome.errors).join(" ")}`.trim(),
        );
        if (outcome.ok) {
            await refresh();
        }
    };

    const searchIndex = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!query.trim()) {
            return;
        }
        setSearchError(null);
        try {
            const result = await getJson<{ hits: DocumentHit[] }>("/api/documents/search", {
                params: { q: query.trim(), limit: 10 },
            });
            setHits(result.hits);
        } catch (err) {
            setHits(null);
            setSearchError(message(err));
        }
    };

    const max = Number(maxMb);
    const maxValid = Number.isFinite(max) && max >= 0.1 && max <= 200;
    const tooBig = file !== null && view !== null && file.size > view.max_file_mb * 1024 * 1024;

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>DOCUMENTI</h1>
                {view && (
                    <span className={styles.badge} data-tone={view.totals.files ? "ok" : undefined}>
                        {view.totals.files} file · {view.totals.chunks} pezzi
                    </span>
                )}
                {view && view.totals.errors > 0 && (
                    <span className={styles.badge} data-tone="warn">
                        {view.totals.errors} non leggibili
                    </span>
                )}
                {note && (
                    <span className={styles.muted} role="status">
                        {note}
                    </span>
                )}
            </div>

            <p className={styles.muted}>
                L&apos;agente cerca nei documenti con il suo tool e li cita come [doc: file#righe]: nelle risposte la
                citazione si apre e mostra il passaggio. Un documento è contenuto esterno: quello che dice sono dati,
                mai istruzioni.
            </p>

            {error && <p className={styles.error}>Documenti non disponibili: {error}</p>}

            {view && (
                <section className={styles.card} aria-label="Cartella di lavoro">
                    <h2 className={styles.h2}>Cartella di lavoro</h2>
                    <dl className={styles.facts}>
                        <dt>Percorso</dt>
                        <dd className={styles.mono}>{view.root}</dd>
                        <dt>Stato</dt>
                        <dd>
                            <span className={styles.badge} data-tone={view.root_exists ? "ok" : "bad"}>
                                {view.root_exists ? "esiste" : "non esiste"}
                            </span>
                        </dd>
                        <dt>Formati</dt>
                        <dd className={styles.mono}>{view.suffixes.join(" ")}</dd>
                    </dl>
                    <p className={styles.help}>
                        La cartella si sceglie all&apos;avvio, dal launcher o da AEHUB_ALLOWED_DIRS. L&apos;indice si
                        aggiorna anche da solo quando l&apos;agente cerca.
                    </p>
                    <div className={styles.filters}>
                        <button type="button" className={`${styles.btn} ${styles.go}`} disabled={busy} onClick={sync}>
                            Sincronizza ora
                        </button>
                        <label className={styles.field}>
                            Dimensione massima (MB)
                            <input
                                type="number"
                                min={0.1}
                                max={200}
                                step={0.5}
                                className={styles.narrow}
                                value={maxMb ?? ""}
                                aria-invalid={!maxValid}
                                onChange={(event) => setMaxMb(event.target.value)}
                            />
                        </label>
                        <button
                            type="button"
                            className={styles.btn}
                            disabled={busy || !maxValid || maxMb === (savedMb || "5")}
                            onClick={saveMax}
                        >
                            Salva
                        </button>
                    </div>
                    {view.stale_vectors > 0 && (
                        <p className={styles.warn}>
                            {view.stale_vectors} pezzi hanno i vettori di un altro modello: ricalcolali da MEMORIA.
                        </p>
                    )}
                </section>
            )}

            <form className={styles.card} onSubmit={upload} aria-label="Carica un documento">
                <h2 className={styles.h2}>Carica un documento</h2>
                <div className={styles.filters}>
                    <label className={`${styles.field} ${styles.grow}`}>
                        File
                        <input
                            type="file"
                            accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
                            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                        />
                    </label>
                    <label className={styles.check}>
                        <input type="checkbox" checked={replace} onChange={(event) => setReplace(event.target.checked)} />
                        sostituisci se esiste
                    </label>
                    <button type="submit" className={`${styles.btn} ${styles.go}`} disabled={busy || !file || tooBig}>
                        Carica
                    </button>
                </div>
                <p className={styles.help}>
                    Il file va nella cartella di lavoro e viene indicizzato subito.
                    {view ? ` Al massimo ${view.max_file_mb} MB.` : ""}
                </p>
                {tooBig && <p className={styles.error}>Il file supera la dimensione massima dei documenti.</p>}
                {uploadError && (
                    <p className={styles.error} role="alert">
                        {uploadError}
                    </p>
                )}
            </form>

            <section className={styles.card} aria-label="Cerca nei documenti">
                <h2 className={styles.h2}>Cerca nei documenti</h2>
                <form className={styles.filters} onSubmit={searchIndex}>
                    <label className={`${styles.field} ${styles.grow}`}>
                        Cerca
                        <input
                            type="search"
                            value={query}
                            placeholder="come lo cercherebbe l'agente"
                            onChange={(event) => setQuery(event.target.value)}
                        />
                    </label>
                    <button type="submit" className={styles.btn} disabled={!query.trim()}>
                        Cerca
                    </button>
                </form>
                {searchError && <p className={styles.error}>{searchError}</p>}
                {hits &&
                    (hits.length ? (
                        <ul className={styles.plain} style={{ display: "grid", gap: 10 }}>
                            {hits.map((hit) => (
                                <li key={hit.citation} className={styles.memory}>
                                    <span className={styles.row}>
                                        <span className={styles.mono}>{hit.path}</span>
                                        <span className={styles.badge}>{locatorLabel(hit.locator)}</span>
                                    </span>
                                    <pre className={styles.pre}>{hit.content}</pre>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className={styles.muted}>Nessun passaggio trovato.</p>
                    ))}
            </section>

            {view && (
                <section className={styles.section} aria-label="File indicizzati">
                    <h2 className={styles.h2}>
                        File indicizzati <span>{view.files.length}</span>
                    </h2>
                    {view.files.length ? (
                        <div className={styles.tableWrap}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>File</th>
                                        <th>Dimensione</th>
                                        <th>Pezzi</th>
                                        <th>Stato</th>
                                        <th>Indicizzato</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {view.files.map((entry) => (
                                        <tr key={entry.path}>
                                            <td className={`${styles.mono} ${styles.task}`}>{entry.path}</td>
                                            <td className={styles.num}>{formatSize(entry.size)}</td>
                                            <td className={styles.num}>{entry.chunks}</td>
                                            <td className={styles.outcome}>
                                                {entry.error ? (
                                                    <span className={styles.error}>{entry.error}</span>
                                                ) : (
                                                    <span className={styles.badge} data-tone="ok">
                                                        cercabile
                                                    </span>
                                                )}
                                            </td>
                                            <td className={styles.num}>{date(entry.indexed_at)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <p className={styles.muted}>Nessun file indicizzato: carica un documento o sincronizza la cartella.</p>
                    )}
                </section>
            )}
        </main>
    );
}
