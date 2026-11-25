/**
 * @file frontend/src/app/control-plane/memory/page.tsx
 * @description Memoria (M11, rewritten in F6, ADR-027): what the assistant
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
import { EMBEDDERS, KIND_TEXT, USER_KINDS, errorText } from "@/lib/nucleo/memory";

function message(err: unknown): string {
    return errorText(err instanceof Error ? err.message : String(err));
}

const SAVED_TEXT: Partial<Record<MemoryKind, string>> = {
    fact: "Fatto salvato.",
    preference: "Preferenza salvata: vale da ogni prossima run.",
    rule: "Regola salvata: vale da ogni prossima run.",
};

interface MemoryForm {
    enabled: boolean;
    similarity: string;
    embedder: string;
    model: string;
}

export default function MemoryPage() {
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
            setError(message(err));
        }
    }, [kind, trust, search]);

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
            setNote(message(err));
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
            return SAVED_TEXT[draftKind] ?? "Ricordo salvato.";
        });
    };

    const update = (memory: Memory, changes: MemoryChanges) =>
        act(async () => {
            await putJson(`/api/memory/${encodeURIComponent(memory.id)}`, changes);
            return changes.trusted ? "Ora è un tuo ricordo." : "Ricordo aggiornato.";
        });

    const forget = (memory: Memory) =>
        void act(async () => {
            await deleteJson(`/api/memory/${encodeURIComponent(memory.id)}`);
            return "Ricordo dimenticato.";
        });

    const purge = () =>
        void act(async () => {
            const result = await deleteJson<{ deleted: number }>("/api/memory", { params: { scope: "untrusted" } });
            setConfirmPurge(false);
            return `${result.deleted} ricordi non affidabili dimenticati.`;
        });

    const reembed = () =>
        void act(async () => {
            const result = await postJson<{ memories: number; documents: number }>("/api/memory/reembed", {});
            return `Vettori ricalcolati: ${result.memories} ricordi, ${result.documents} pezzi di documenti.`;
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
                ? "Impostazioni della memoria salvate: valgono dalla prossima run."
                : `${outcome.message ?? "Non salvato."} ${Object.values(outcome.errors).join(" ")}`.trim(),
        );
        if (outcome.ok) {
            await refresh();
        }
    };

    const status = data?.status;

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>MEMORIA</h1>
                {status && (
                    <>
                        <span className={styles.badge} data-tone={status.enabled ? "ok" : undefined}>
                            {status.enabled ? "accesa" : "spenta"}
                        </span>
                        <span className={styles.badge}>{status.total} ricordi</span>
                        {status.untrusted > 0 && (
                            <span className={styles.badge} data-tone="warn">
                                {status.untrusted} non affidabili
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

            {error && <p className={styles.error}>Memoria non disponibile: {error}</p>}

            {form && (
                <section className={styles.card} aria-label="Come ricorda">
                    <h2 className={styles.h2}>Come ricorda</h2>
                    <div className={styles.filters}>
                        <label className={styles.check}>
                            <span className={styles.switch}>
                                <input
                                    type="checkbox"
                                    role="switch"
                                    checked={form.enabled}
                                    aria-label="Memoria a lungo termine"
                                    onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
                                />
                                <span aria-hidden="true" />
                            </span>
                            {form.enabled ? "accesa" : "spenta"}
                        </label>
                        <label className={styles.field}>
                            Somiglianza minima
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
                    <p className={styles.help}>
                        Accesa, ogni run richiama i ricordi utili e salva quello che impara. Più alta la somiglianza,
                        meno ricordi richiamati per significato (le parole uguali valgono sempre).
                    </p>

                    <div className={styles.row} role="radiogroup" aria-label="Embedding">
                        {Object.entries(EMBEDDERS).map(([name, info]) => (
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
                    <p className={styles.help}>{EMBEDDERS[form.embedder]?.help}</p>
                    {form.embedder === "sentence-transformers" && (
                        <label className={`${styles.field} ${styles.grow}`} style={{ maxWidth: 420 }}>
                            Modello (384 dimensioni)
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
                            Salva
                        </button>
                        {dirty && (
                            <button type="button" className={styles.btn} onClick={() => saved && setForm(saved)}>
                                Annulla
                            </button>
                        )}
                    </div>

                    {status && status.stale_vectors > 0 && (
                        <div className={styles.issue} data-tone="warn">
                            <span>
                                {status.stale_vectors} ricordi hanno i vettori di un altro modello: si trovano solo per
                                parole finché non li ricalcoli.
                            </span>
                            <button type="button" className={styles.linkBtn} disabled={busy} onClick={reembed}>
                                Ricalcola i vettori
                            </button>
                        </div>
                    )}
                </section>
            )}

            <form className={styles.card} onSubmit={add} aria-label="Aggiungi un ricordo">
                <h2 className={styles.h2}>Aggiungi un ricordo</h2>
                <div className={styles.filters}>
                    <label className={styles.field}>
                        Tipo
                        <select value={draftKind} onChange={(event) => setDraftKind(event.target.value as MemoryKind)}>
                            {USER_KINDS.map((item) => (
                                <option key={item} value={item}>
                                    {KIND_TEXT[item].label}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className={`${styles.field} ${styles.grow}`}>
                        Testo
                        <input
                            value={draft}
                            maxLength={1200}
                            placeholder={
                                draftKind === "fact"
                                    ? "es. La mia auto è una Panda rossa."
                                    : "es. Rispondi in italiano, con riassunti di cinque righe."
                            }
                            onChange={(event) => setDraft(event.target.value)}
                        />
                    </label>
                    <button type="submit" className={`${styles.btn} ${styles.go}`} disabled={busy || !draft.trim()}>
                        Salva
                    </button>
                </div>
                <p className={styles.help}>{KIND_TEXT[draftKind].help} Scritto da te, conta come affidabile.</p>
            </form>

            <section className={styles.section} aria-label="Ricordi">
                <h2 className={styles.h2}>
                    Ricordi <span>{data?.memories.length ?? 0}</span>
                </h2>
                <form
                    className={styles.filters}
                    onSubmit={(event) => {
                        event.preventDefault();
                        setSearch(query.trim());
                    }}
                >
                    <label className={`${styles.field} ${styles.grow}`}>
                        Cerca
                        <input
                            type="search"
                            value={query}
                            placeholder="parole o significato"
                            onChange={(event) => {
                                setQuery(event.target.value);
                                if (!event.target.value.trim()) {
                                    setSearch("");
                                }
                            }}
                        />
                    </label>
                    <label className={styles.field}>
                        Tipo
                        <select value={kind} onChange={(event) => setKind(event.target.value as MemoryKind | "")}>
                            <option value="">tutti</option>
                            {(["fact", "preference", "rule", "episode"] as MemoryKind[]).map((item) => (
                                <option key={item} value={item}>
                                    {KIND_TEXT[item].label}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className={styles.field}>
                        Fonte
                        <select value={trust} onChange={(event) => setTrust(event.target.value as TrustFilter)}>
                            <option value="all">tutte</option>
                            <option value="trusted">affidabili</option>
                            <option value="untrusted">non affidabili</option>
                        </select>
                    </label>
                    <button type="submit" className={styles.btn}>
                        Cerca
                    </button>
                </form>

                {status && status.untrusted > 0 && (
                    <div className={styles.issue} data-tone="warn">
                        <span>
                            I ricordi non affidabili sono stati scritti dopo aver letto web, file o server MCP: si
                            richiamano come dati, mai come istruzioni.
                        </span>
                        {confirmPurge ? (
                            <>
                                <button
                                    type="button"
                                    className={`${styles.btn} ${styles.danger}`}
                                    disabled={busy}
                                    onClick={purge}
                                >
                                    Conferma: dimentica {status.untrusted}
                                </button>
                                <button type="button" className={styles.linkBtn} onClick={() => setConfirmPurge(false)}>
                                    Annulla
                                </button>
                            </>
                        ) : (
                            <button type="button" className={styles.linkBtn} onClick={() => setConfirmPurge(true)}>
                                Dimentica i non affidabili
                            </button>
                        )}
                    </div>
                )}

                {data && <MemoryList memories={data.memories} busy={busy} onSave={update} onForget={forget} />}
            </section>
        </main>
    );
}
