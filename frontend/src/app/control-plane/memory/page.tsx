/**
 * @file frontend/src/app/control-plane/memory/page.tsx
 * @description Memory (M11, rewritten in F6, ADR-027): what the assistant
 * remembers across sessions, and how it remembers.
 *
 * - Settings (PUT /api/settings, no restart): memory on or off, the
 *   similarity threshold of recall, the embedder and its model. After an
 *   embedder change, POST /api/memory/reembed recomputes the old vectors.
 * - Add a fact, preference or rule (POST /api/memory): it is the user's, so
 *   trusted; preferences and rules reach every run.
 * - Browse and search (GET /api/memory with q: the engine's hybrid
 *   retrieval), filter by kind and trust, edit in place, vouch for an
 *   untrusted memory, forget one or all the untrusted ones.
 */
"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

import MemoryList from "@/components/control-plane/MemoryList";
import styles from "@/components/control-plane/control.module.css";
import { deleteJson, getJson, postJson, putJson } from "@/lib/api/client";
import {
    memoryOn,
    type Memory,
    type MemoryChanges,
    type MemoryKind,
    type MemoryView,
    type TrustFilter,
} from "@/lib/api/memory";
import { useSettings } from "@/lib/api/settings";
import { catalog, useLanguage, type Lang } from "@/lib/i18n";
import { EMBEDDERS, KIND_TEXT, USER_KINDS, errorText } from "@/lib/nucleo/memory";

function message(err: unknown, lang: Lang): string {
    return errorText(err instanceof Error ? err.message : String(err), lang);
}

const TEXT = catalog({
    en: {
        saved: { fact: "Fact saved.", preference: "Preference saved: it applies from every next run.", rule: "Rule saved: it applies from every next run." } as Partial<Record<MemoryKind, string>>,
        memorySaved: "Memory saved.",
        nowYours: "It is now your memory.",
        updated: "Memory updated.",
        forgotten: "Memory forgotten.",
        purged: (count: number) => `${count} untrusted memories forgotten.`,
        reembedded: (memories: number, documents: number) =>
            `Vectors recomputed: ${memories} memories, ${documents} pieces of documents.`,
        settingsSaved: "Memory settings saved: they apply from the next run.",
        notSaved: "Not saved.",
        title: "MEMORY",
        on: "on",
        off: "off",
        count: (count: number) => `${count} memories`,
        untrusted: (count: number) => `${count} untrusted`,
        unavailable: "Memory not available:",
        how: "How it remembers",
        longTerm: "Long-term memory",
        similarity: "Minimum similarity",
        help: "When on, every run recalls the useful memories and saves what it learns. The higher the similarity, the fewer memories recalled by meaning (the same words always count).",
        model: "Model (384 dimensions)",
        save: "Save",
        cancel: "Cancel",
        stale: (count: number) =>
            `${count} memories have the vectors of another model: they are found only by words until you recompute them.`,
        recompute: "Recompute the vectors",
        add: "Add a memory",
        kind: "Kind",
        text: "Text",
        factExample: "e.g. My car is a red Panda.",
        ruleExample: "e.g. Answer in English, with five-line summaries.",
        written: "Written by you, it counts as trusted.",
        memories: "Memories",
        search: "Search",
        searchPlaceholder: "words or meaning",
        all: "all",
        source: "Source",
        allSources: "all",
        trusted: "trusted",
        untrustedOption: "untrusted",
        untrustedHelp:
            "Untrusted memories were written after reading the web, files or MCP servers: they are recalled as data, never as instructions.",
        confirmPurge: (count: number) => `Confirm: forget ${count}`,
        purge: "Forget the untrusted ones",
    },
    it: {
        saved: { fact: "Fatto salvato.", preference: "Preferenza salvata: vale da ogni prossima run.", rule: "Regola salvata: vale da ogni prossima run." } as Partial<Record<MemoryKind, string>>,
        memorySaved: "Ricordo salvato.",
        nowYours: "Ora è un tuo ricordo.",
        updated: "Ricordo aggiornato.",
        forgotten: "Ricordo dimenticato.",
        purged: (count: number) => `${count} ricordi non affidabili dimenticati.`,
        reembedded: (memories: number, documents: number) =>
            `Vettori ricalcolati: ${memories} ricordi, ${documents} pezzi di documenti.`,
        settingsSaved: "Impostazioni della memoria salvate: valgono dalla prossima run.",
        notSaved: "Non salvato.",
        title: "MEMORIA",
        on: "accesa",
        off: "spenta",
        count: (count: number) => `${count} ricordi`,
        untrusted: (count: number) => `${count} non affidabili`,
        unavailable: "Memoria non disponibile:",
        how: "Come ricorda",
        longTerm: "Memoria a lungo termine",
        similarity: "Somiglianza minima",
        help: "Accesa, ogni run richiama i ricordi utili e salva quello che impara. Più alta la somiglianza, meno ricordi richiamati per significato (le parole uguali valgono sempre).",
        model: "Modello (384 dimensioni)",
        save: "Salva",
        cancel: "Annulla",
        stale: (count: number) =>
            `${count} ricordi hanno i vettori di un altro modello: si trovano solo per parole finché non li ricalcoli.`,
        recompute: "Ricalcola i vettori",
        add: "Aggiungi un ricordo",
        kind: "Tipo",
        text: "Testo",
        factExample: "es. La mia auto è una Panda rossa.",
        ruleExample: "es. Rispondi in italiano, con riassunti di cinque righe.",
        written: "Scritto da te, conta come affidabile.",
        memories: "Ricordi",
        search: "Cerca",
        searchPlaceholder: "parole o significato",
        all: "tutti",
        source: "Fonte",
        allSources: "tutte",
        trusted: "affidabili",
        untrustedOption: "non affidabili",
        untrustedHelp:
            "I ricordi non affidabili sono stati scritti dopo aver letto web, file o server MCP: si richiamano come dati, mai come istruzioni.",
        confirmPurge: (count: number) => `Conferma: dimentica ${count}`,
        purge: "Dimentica i non affidabili",
    },
});

interface MemoryForm {
    enabled: boolean;
    similarity: string;
    embedder: string;
    model: string;
}

export default function MemoryPage() {
    const lang = useLanguage();
    const t = TEXT[lang];
    const { view: settings, save } = useSettings();
    const [data, setData] = useState<MemoryView | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [note, setNote] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [kind, setKind] = useState<MemoryKind | "">("");
    const [trust, setTrust] = useState<TrustFilter>("all");
    const [query, setQuery] = useState("");
    const [search, setSearch] = useState("");
    const [draft, setDraft] = useState("");
    const [draftKind, setDraftKind] = useState<MemoryKind>("fact");
    const [form, setForm] = useState<MemoryForm | null>(null);
    const [confirmPurge, setConfirmPurge] = useState(false);

    const saved = useMemo<MemoryForm | null>(() => {
        if (!settings) {
            return null;
        }
        const value = (name: string) => settings.settings.find((field) => field.name === name)?.value ?? "";
        return {
            enabled: memoryOn(value("AEHUB_MEMORY_ENABLED")),
            similarity: value("AEHUB_MEMORY_MIN_SIMILARITY") || "0.25",
            embedder: value("AEHUB_EMBEDDER") || "sentence-transformers",
            model: value("AEHUB_EMBEDDING_MODEL") || "all-MiniLM-L6-v2",
        };
    }, [settings]);

    useEffect(() => {
        if (saved) {
            const reset = setTimeout(() => setForm(saved), 0);
            return () => clearTimeout(reset);
        }
    }, [saved]);

    const refresh = useCallback(async () => {
        const params: Record<string, string | number> = { limit: 500, trust };
        if (kind) {
            params.kind = kind;
        }
        if (search) {
            params.q = search;
            params.limit = 50;
        }
        try {
            setData(await getJson<MemoryView>("/api/memory", { params }));
            setError(null);
        } catch (err) {
            setError(message(err, lang));
        }
    }, [kind, trust, search, lang]);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    const act = async (work: () => Promise<string>) => {
        setBusy(true);
        setNote(null);
        try {
            setNote(await work());
            await refresh();
            return true;
        } catch (err) {
            setNote(message(err, lang));
            return false;
        } finally {
            setBusy(false);
        }
    };

    const add = (event: React.FormEvent) => {
        event.preventDefault();
        void act(async () => {
            await postJson("/api/memory", { content: draft.trim(), kind: draftKind });
            setDraft("");
            return t.saved[draftKind] ?? t.memorySaved;
        });
    };

    const update = (memory: Memory, changes: MemoryChanges) =>
        act(async () => {
            await putJson(`/api/memory/${encodeURIComponent(memory.id)}`, changes);
            return changes.trusted ? t.nowYours : t.updated;
        });

    const forget = (memory: Memory) =>
        void act(async () => {
            await deleteJson(`/api/memory/${encodeURIComponent(memory.id)}`);
            return t.forgotten;
        });

    const purge = () =>
        void act(async () => {
            const result = await deleteJson<{ deleted: number }>("/api/memory", { params: { scope: "untrusted" } });
            setConfirmPurge(false);
            return t.purged(result.deleted);
        });

    const reembed = () =>
        void act(async () => {
            const result = await postJson<{ memories: number; documents: number }>("/api/memory/reembed", {});
            return t.reembedded(result.memories, result.documents);
        });

    const similarity = Number(form?.similarity);
    const similarityValid = Number.isFinite(similarity) && similarity > 0 && similarity <= 1;
    const modelValid = !form || form.embedder !== "sentence-transformers" || /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}(\/[A-Za-z0-9._-]{1,96})?$/.test(form.model);
    const dirty =
        form !== null &&
        saved !== null &&
        (form.enabled !== saved.enabled ||
            form.similarity !== saved.similarity ||
            form.embedder !== saved.embedder ||
            form.model !== saved.model);

    const saveSettings = async () => {
        if (!form || !saved) {
            return;
        }
        const changes: Record<string, string> = {};
        if (form.enabled !== saved.enabled) {
            changes.AEHUB_MEMORY_ENABLED = form.enabled ? "on" : "off";
        }
        if (form.similarity !== saved.similarity) {
            changes.AEHUB_MEMORY_MIN_SIMILARITY = String(similarity);
        }
        if (form.embedder !== saved.embedder) {
            changes.AEHUB_EMBEDDER = form.embedder;
        }
        if (form.model !== saved.model) {
            changes.AEHUB_EMBEDDING_MODEL = form.model.trim();
        }
        setBusy(true);
        const outcome = await save(changes);
        setBusy(false);
        setNote(
            outcome.ok
                ? t.settingsSaved
                : `${outcome.message ?? t.notSaved} ${Object.values(outcome.errors).join(" ")}`.trim(),
        );
        if (outcome.ok) {
            await refresh();
        }
    };

    const status = data?.status;

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>{t.title}</h1>
                {status && (
                    <>
                        <span className={styles.badge} data-tone={status.enabled ? "ok" : undefined}>
                            {status.enabled ? t.on : t.off}
                        </span>
                        <span className={styles.badge}>{t.count(status.total)}</span>
                        {status.untrusted > 0 && (
                            <span className={styles.badge} data-tone="warn">
                                {t.untrusted(status.untrusted)}
                            </span>
                        )}
                    </>
                )}
                {note && (
                    <span className={styles.muted} role="status">
                        {note}
                    </span>
                )}
            </div>

            {error && (
                <p className={styles.error}>
                    {t.unavailable} {error}
                </p>
            )}

            {form && (
                <section className={styles.card} aria-label={t.how}>
                    <h2 className={styles.h2}>{t.how}</h2>
                    <div className={styles.filters}>
                        <label className={styles.check}>
                            <span className={styles.switch}>
                                <input
                                    type="checkbox"
                                    role="switch"
                                    checked={form.enabled}
                                    aria-label={t.longTerm}
                                    onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
                                />
                                <span aria-hidden="true" />
                            </span>
                            {form.enabled ? t.on : t.off}
                        </label>
                        <label className={styles.field}>
                            {t.similarity}
                            <input
                                type="number"
                                min={0.05}
                                max={1}
                                step={0.05}
                                className={styles.narrow}
                                value={form.similarity}
                                aria-invalid={!similarityValid}
                                onChange={(event) => setForm({ ...form, similarity: event.target.value })}
                            />
                        </label>
                    </div>
                    <p className={styles.help}>{t.help}</p>

                    <div className={styles.row} role="radiogroup" aria-label="Embedding">
                        {Object.entries(EMBEDDERS[lang]).map(([name, info]) => (
                            <label key={name} className={styles.check}>
                                <input
                                    type="radio"
                                    name="embedder"
                                    checked={form.embedder === name}
                                    onChange={() => setForm({ ...form, embedder: name })}
                                />
                                {info.label}
                            </label>
                        ))}
                    </div>
                    <p className={styles.help}>{EMBEDDERS[lang][form.embedder]?.help}</p>
                    {form.embedder === "sentence-transformers" && (
                        <label className={`${styles.field} ${styles.grow}`} style={{ maxWidth: 420 }}>
                            {t.model}
                            <input
                                value={form.model}
                                spellCheck={false}
                                aria-invalid={!modelValid}
                                onChange={(event) => setForm({ ...form, model: event.target.value })}
                            />
                        </label>
                    )}

                    <div className={styles.row}>
                        <button
                            type="button"
                            className={`${styles.btn} ${styles.go}`}
                            disabled={busy || !dirty || !similarityValid || !modelValid}
                            onClick={saveSettings}
                        >
                            {t.save}
                        </button>
                        {dirty && (
                            <button type="button" className={styles.btn} onClick={() => saved && setForm(saved)}>
                                {t.cancel}
                            </button>
                        )}
                    </div>

                    {status && status.stale_vectors > 0 && (
                        <div className={styles.issue} data-tone="warn">
                            <span>{t.stale(status.stale_vectors)}</span>
                            <button type="button" className={styles.linkBtn} disabled={busy} onClick={reembed}>
                                {t.recompute}
                            </button>
                        </div>
                    )}
                </section>
            )}

            <form className={styles.card} onSubmit={add} aria-label={t.add}>
                <h2 className={styles.h2}>{t.add}</h2>
                <div className={styles.filters}>
                    <label className={styles.field}>
                        {t.kind}
                        <select value={draftKind} onChange={(event) => setDraftKind(event.target.value as MemoryKind)}>
                            {USER_KINDS.map((item) => (
                                <option key={item} value={item}>
                                    {KIND_TEXT[lang][item].label}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className={`${styles.field} ${styles.grow}`}>
                        {t.text}
                        <input
                            value={draft}
                            maxLength={1200}
                            placeholder={draftKind === "fact" ? t.factExample : t.ruleExample}
                            onChange={(event) => setDraft(event.target.value)}
                        />
                    </label>
                    <button type="submit" className={`${styles.btn} ${styles.go}`} disabled={busy || !draft.trim()}>
                        {t.save}
                    </button>
                </div>
                <p className={styles.help}>
                    {KIND_TEXT[lang][draftKind].help} {t.written}
                </p>
            </form>

            <section className={styles.section} aria-label={t.memories}>
                <h2 className={styles.h2}>
                    {t.memories} <span>{data?.memories.length ?? 0}</span>
                </h2>
                <form
                    className={styles.filters}
                    onSubmit={(event) => {
                        event.preventDefault();
                        setSearch(query.trim());
                    }}
                >
                    <label className={`${styles.field} ${styles.grow}`}>
                        {t.search}
                        <input
                            type="search"
                            value={query}
                            placeholder={t.searchPlaceholder}
                            onChange={(event) => {
                                setQuery(event.target.value);
                                if (!event.target.value.trim()) {
                                    setSearch("");
                                }
                            }}
                        />
                    </label>
                    <label className={styles.field}>
                        {t.kind}
                        <select value={kind} onChange={(event) => setKind(event.target.value as MemoryKind | "")}>
                            <option value="">{t.all}</option>
                            {(["fact", "preference", "rule", "episode"] as MemoryKind[]).map((item) => (
                                <option key={item} value={item}>
                                    {KIND_TEXT[lang][item].label}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className={styles.field}>
                        {t.source}
                        <select value={trust} onChange={(event) => setTrust(event.target.value as TrustFilter)}>
                            <option value="all">{t.allSources}</option>
                            <option value="trusted">{t.trusted}</option>
                            <option value="untrusted">{t.untrustedOption}</option>
                        </select>
                    </label>
                    <button type="submit" className={styles.btn}>
                        {t.search}
                    </button>
                </form>

                {status && status.untrusted > 0 && (
                    <div className={styles.issue} data-tone="warn">
                        <span>{t.untrustedHelp}</span>
                        {confirmPurge ? (
                            <>
                                <button
                                    type="button"
                                    className={`${styles.btn} ${styles.danger}`}
                                    disabled={busy}
                                    onClick={purge}
                                >
                                    {t.confirmPurge(status.untrusted)}
                                </button>
                                <button type="button" className={styles.linkBtn} onClick={() => setConfirmPurge(false)}>
                                    {t.cancel}
                                </button>
                            </>
                        ) : (
                            <button type="button" className={styles.linkBtn} onClick={() => setConfirmPurge(true)}>
                                {t.purge}
                            </button>
                        )}
                    </div>
                )}

                {data && <MemoryList memories={data.memories} busy={busy} onSave={update} onForget={forget} />}
            </section>
        </main>
    );
}
