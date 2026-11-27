/**
 * @file frontend/src/app/control-plane/documents/page.tsx
 * @description Documents (F6, ADR-027): the user's documents in the working
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
import { catalog, localeOf, useLanguage, type Lang } from "@/lib/i18n";
import { useSettings } from "@/lib/api/settings";
import { errorText } from "@/lib/nucleo/memory";

const TEXT = catalog({
    en: {
        noFolder: "The working folder does not exist.",
        added: (count: number) => `${count} added`,
        updated: (count: number) => `${count} updated`,
        removed: (count: number) => `${count} removed`,
        failed: (count: number) => `${count} with errors`,
        pending: (count: number) => `${count} waiting`,
        synced: (parts: string) => `Synchronized: ${parts}.`,
        nothingNew: "Synchronized: nothing new.",
        uploaded: (path: string, summary: string) => `${path} uploaded. ${summary}`,
        maxSaved: "Maximum size saved: it applies from the next synchronization.",
        notSaved: "Not saved.",
        title: "DOCUMENTS",
        totals: (files: number, chunks: number) => `${files} files · ${chunks} pieces`,
        unreadable: (count: number) => `${count} unreadable`,
        intro:
            "The agent searches the documents with its tool and cites them as [doc: file#lines]: in the answers the citation opens and shows the passage. A document is external content: what it says is data, never instructions.",
        unavailable: "Documents not available:",
        folder: "Working folder",
        path: "Path",
        state: "State",
        exists: "exists",
        missing: "does not exist",
        formats: "Formats",
        agentFolders: "Agents' folders",
        agentFoldersHelp: "Indexed too, with their full path in the citations. They are chosen in TOOLS.",
        folderHelp:
            "The folder is chosen at start, by the launcher or with AEHUB_ALLOWED_DIRS. The index also updates by itself when the agent searches.",
        syncNow: "Synchronize now",
        maxSize: "Maximum size (MB)",
        save: "Save",
        stale: (count: number) => `${count} pieces have the vectors of another model: recompute them from MEMORY.`,
        upload: "Upload a document",
        file: "File",
        replace: "replace if it exists",
        send: "Upload",
        uploadHelp: "The file goes into the working folder and is indexed at once.",
        atMost: (mb: number) => ` At most ${mb} MB.`,
        tooBig: "The file is larger than the maximum size of the documents.",
        searchTitle: "Search the documents",
        search: "Search",
        searchPlaceholder: "as the agent would search it",
        noHits: "No passage found.",
        indexed: "Indexed files",
        size: "Size",
        pieces: "Pieces",
        indexedAt: "Indexed",
        searchable: "searchable",
        noFiles: "No file indexed: upload a document or synchronize the folder.",
    },
    it: {
        noFolder: "La cartella di lavoro non esiste.",
        added: (count: number) => `${count} aggiunti`,
        updated: (count: number) => `${count} aggiornati`,
        removed: (count: number) => `${count} tolti`,
        failed: (count: number) => `${count} con errori`,
        pending: (count: number) => `${count} in attesa`,
        synced: (parts: string) => `Sincronizzato: ${parts}.`,
        nothingNew: "Sincronizzato: niente di nuovo.",
        uploaded: (path: string, summary: string) => `${path} caricato. ${summary}`,
        maxSaved: "Dimensione massima salvata: vale dalla prossima sincronizzazione.",
        notSaved: "Non salvato.",
        title: "DOCUMENTI",
        totals: (files: number, chunks: number) => `${files} file · ${chunks} pezzi`,
        unreadable: (count: number) => `${count} non leggibili`,
        intro:
            "L'agente cerca nei documenti con il suo tool e li cita come [doc: file#righe]: nelle risposte la citazione si apre e mostra il passaggio. Un documento è contenuto esterno: quello che dice sono dati, mai istruzioni.",
        unavailable: "Documenti non disponibili:",
        folder: "Cartella di lavoro",
        path: "Percorso",
        state: "Stato",
        exists: "esiste",
        missing: "non esiste",
        formats: "Formati",
        agentFolders: "Cartelle degli agenti",
        agentFoldersHelp: "Indicizzate anche loro, con il percorso completo nelle citazioni. Si scelgono in STRUMENTI.",
        folderHelp:
            "La cartella si sceglie all'avvio, dal launcher o da AEHUB_ALLOWED_DIRS. L'indice si aggiorna anche da solo quando l'agente cerca.",
        syncNow: "Sincronizza ora",
        maxSize: "Dimensione massima (MB)",
        save: "Salva",
        stale: (count: number) => `${count} pezzi hanno i vettori di un altro modello: ricalcolali da MEMORIA.`,
        upload: "Carica un documento",
        file: "File",
        replace: "sostituisci se esiste",
        send: "Carica",
        uploadHelp: "Il file va nella cartella di lavoro e viene indicizzato subito.",
        atMost: (mb: number) => ` Al massimo ${mb} MB.`,
        tooBig: "Il file supera la dimensione massima dei documenti.",
        searchTitle: "Cerca nei documenti",
        search: "Cerca",
        searchPlaceholder: "come lo cercherebbe l'agente",
        noHits: "Nessun passaggio trovato.",
        indexed: "File indicizzati",
        size: "Dimensione",
        pieces: "Pezzi",
        indexedAt: "Indicizzato",
        searchable: "cercabile",
        noFiles: "Nessun file indicizzato: carica un documento o sincronizza la cartella.",
    },
});

function message(err: unknown, lang: Lang): string {
    return errorText(err instanceof Error ? err.message : String(err), lang);
}

function syncSummary(report: SyncReport, lang: Lang): string {
    const t = TEXT[lang];
    if (!report.root_exists && !(report.folders ?? []).length) {
        return t.noFolder;
    }
    const parts = [
        report.added.length && t.added(report.added.length),
        report.updated.length && t.updated(report.updated.length),
        report.removed.length && t.removed(report.removed.length),
        report.failed.length && t.failed(report.failed.length),
        report.pending && t.pending(report.pending),
    ].filter(Boolean);
    return parts.length ? t.synced(parts.join(", ")) : t.nothingNew;
}

function date(value: string | null, lang: Lang): string {
    if (!value) {
        return "-";
    }
    const parsed = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
    return Number.isNaN(parsed.getTime())
        ? value
        : parsed.toLocaleString(localeOf(lang), { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function DocumentsPage() {
    const lang = useLanguage();
    const t = TEXT[lang];
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
            setError(message(err, lang));
        }
    }, [lang]);

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
            setNote(syncSummary(await postJson<SyncReport>("/api/documents/sync", {}), lang));
            await refresh();
        } catch (err) {
            setNote(message(err, lang));
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
            setNote(t.uploaded(result.path, syncSummary(result.sync, lang)));
            setFile(null);
            setReplace(false);
            (event.target as HTMLFormElement).reset();
            await refresh();
        } catch (err) {
            setUploadError(message(err, lang));
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
                ? t.maxSaved
                : `${outcome.message ?? t.notSaved} ${Object.values(outcome.errors).join(" ")}`.trim(),
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
            setSearchError(message(err, lang));
        }
    };

    const max = Number(maxMb);
    const maxValid = Number.isFinite(max) && max >= 0.1 && max <= 200;
    const tooBig = file !== null && view !== null && file.size > view.max_file_mb * 1024 * 1024;

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>{t.title}</h1>
                {view && (
                    <span className={styles.badge} data-tone={view.totals.files ? "ok" : undefined}>
                        {t.totals(view.totals.files, view.totals.chunks)}
                    </span>
                )}
                {view && view.totals.errors > 0 && (
                    <span className={styles.badge} data-tone="warn">
                        {t.unreadable(view.totals.errors)}
                    </span>
                )}
                {note && (
                    <span className={styles.muted} role="status">
                        {note}
                    </span>
                )}
            </div>

            <p className={styles.muted}>{t.intro}</p>

            {error && (
                <p className={styles.error}>
                    {t.unavailable} {error}
                </p>
            )}

            {view && (
                <section className={styles.card} aria-label={t.folder}>
                    <h2 className={styles.h2}>{t.folder}</h2>
                    <dl className={styles.facts}>
                        <dt>{t.path}</dt>
                        <dd className={styles.mono}>{view.root}</dd>
                        <dt>{t.state}</dt>
                        <dd>
                            <span className={styles.badge} data-tone={view.root_exists ? "ok" : "bad"}>
                                {view.root_exists ? t.exists : t.missing}
                            </span>
                        </dd>
                        {(view.folders ?? []).length > 0 && (
                            <>
                                <dt>{t.agentFolders}</dt>
                                <dd>
                                    <ul className={styles.mono} aria-label={t.agentFolders}>
                                        {(view.folders ?? []).map((folder) => (
                                            <li key={folder.path}>
                                                {folder.path}{" "}
                                                <span className={styles.badge} data-tone={folder.exists ? "ok" : "bad"}>
                                                    {folder.exists ? t.exists : t.missing}
                                                </span>
                                            </li>
                                        ))}
                                    </ul>
                                    <span className={styles.help}>{t.agentFoldersHelp}</span>
                                </dd>
                            </>
                        )}
                        <dt>{t.formats}</dt>
                        <dd className={styles.mono}>{view.suffixes.join(" ")}</dd>
                    </dl>
                    <p className={styles.help}>{t.folderHelp}</p>
                    <div className={styles.filters}>
                        <button type="button" className={`${styles.btn} ${styles.go}`} disabled={busy} onClick={sync}>
                            {t.syncNow}
                        </button>
                        <label className={styles.field}>
                            {t.maxSize}
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
                            {t.save}
                        </button>
                    </div>
                    {view.stale_vectors > 0 && (
                        <p className={styles.warn}>{t.stale(view.stale_vectors)}</p>
                    )}
                </section>
            )}

            <form className={styles.card} onSubmit={upload} aria-label={t.upload}>
                <h2 className={styles.h2}>{t.upload}</h2>
                <div className={styles.filters}>
                    <label className={`${styles.field} ${styles.grow}`}>
                        {t.file}
                        <input
                            type="file"
                            accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
                            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                        />
                    </label>
                    <label className={styles.check}>
                        <input type="checkbox" checked={replace} onChange={(event) => setReplace(event.target.checked)} />
                        {t.replace}
                    </label>
                    <button type="submit" className={`${styles.btn} ${styles.go}`} disabled={busy || !file || tooBig}>
                        {t.send}
                    </button>
                </div>
                <p className={styles.help}>
                    {t.uploadHelp}
                    {view ? t.atMost(view.max_file_mb) : ""}
                </p>
                {tooBig && <p className={styles.error}>{t.tooBig}</p>}
                {uploadError && (
                    <p className={styles.error} role="alert">
                        {uploadError}
                    </p>
                )}
            </form>

            <section className={styles.card} aria-label={t.searchTitle}>
                <h2 className={styles.h2}>{t.searchTitle}</h2>
                <form className={styles.filters} onSubmit={searchIndex}>
                    <label className={`${styles.field} ${styles.grow}`}>
                        {t.search}
                        <input
                            type="search"
                            value={query}
                            placeholder={t.searchPlaceholder}
                            onChange={(event) => setQuery(event.target.value)}
                        />
                    </label>
                    <button type="submit" className={styles.btn} disabled={!query.trim()}>
                        {t.search}
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
                                        <span className={styles.badge}>{locatorLabel(hit.locator, lang)}</span>
                                    </span>
                                    <pre className={styles.pre}>{hit.content}</pre>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className={styles.muted}>{t.noHits}</p>
                    ))}
            </section>

            {view && (
                <section className={styles.section} aria-label={t.indexed}>
                    <h2 className={styles.h2}>
                        {t.indexed} <span>{view.files.length}</span>
                    </h2>
                    {view.files.length ? (
                        <div className={styles.tableWrap}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>{t.file}</th>
                                        <th>{t.size}</th>
                                        <th>{t.pieces}</th>
                                        <th>{t.state}</th>
                                        <th>{t.indexedAt}</th>
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
                                                        {t.searchable}
                                                    </span>
                                                )}
                                            </td>
                                            <td className={styles.num}>{date(entry.indexed_at, lang)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <p className={styles.muted}>{t.noFiles}</p>
                    )}
                </section>
            )}
        </main>
    );
}
