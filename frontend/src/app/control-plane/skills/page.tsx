/**
 * @file frontend/src/app/control-plane/skills/page.tsx
 * @description Skill (F5, ADR-026): import a skill in the SKILL.md format
 * (Claude Code, Codex, OpenClaw) from a link or a file, read it, turn it on
 * or off, remove it.
 *
 * A skill is imported off, and the page shows its whole text and the
 * warnings found in it before it can be turned on. Only the text is
 * imported: files the skill bundles are not, and nothing runs. The agent
 * reads an enabled skill through the use_skill tool as untrusted content,
 * so after reading it every high-risk action waits for an approval.
 *
 * GET /api/skills, GET /api/skills/{id}, POST /api/skills/import,
 * PUT /api/skills/{id}, DELETE /api/skills/{id}; every change is audited.
 */
"use client";

import React, { useCallback, useEffect, useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import { deleteJson, getJson, postJson, putJson } from "@/lib/api/client";
import type { ImportedSkill, ImportedSkillDetail } from "@/lib/api/tools";
import { WARNING_TEXT, importErrorText, sourceLabel } from "@/lib/nucleo/tools";

function message(err: unknown): string {
    return err instanceof Error ? err.message : String(err);
}

/** The text of a chosen file (FileReader where File.text is missing). */
function readText(file: File): Promise<string> {
    if (typeof file.text === "function") {
        return file.text();
    }
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result ?? ""));
        reader.onerror = () => reject(reader.error);
        reader.readAsText(file);
    });
}

function StateBadge({ skill }: { skill: ImportedSkill }) {
    return skill.enabled ? (
        <span className={styles.badge} data-tone="ok">
            accesa
        </span>
    ) : (
        <span className={styles.badge}>spenta</span>
    );
}

function SkillDetail({
    skill,
    busy,
    onToggle,
    onDelete,
}: {
    skill: ImportedSkillDetail;
    busy: boolean;
    onToggle: (enabled: boolean) => void;
    onDelete: () => void;
}) {
    const [confirming, setConfirming] = useState(false);

    return (
        <section className={styles.card} aria-label={`Skill ${skill.name}`}>
            <div className={styles.head}>
                <h2 className={styles.runTitle}>{skill.name}</h2>
                <StateBadge skill={skill} />
                <div className={styles.headEnd}>
                    {skill.enabled ? (
                        <button type="button" className={styles.btn} disabled={busy} onClick={() => onToggle(false)}>
                            Spegni
                        </button>
                    ) : (
                        <button
                            type="button"
                            className={`${styles.btn} ${styles.go}`}
                            disabled={busy}
                            onClick={() => onToggle(true)}
                        >
                            Accendi
                        </button>
                    )}
                    {confirming ? (
                        <>
                            <button
                                type="button"
                                className={`${styles.btn} ${styles.danger}`}
                                disabled={busy}
                                onClick={onDelete}
                            >
                                Conferma: elimina
                            </button>
                            <button type="button" className={styles.btn} onClick={() => setConfirming(false)}>
                                Annulla
                            </button>
                        </>
                    ) : (
                        <button
                            type="button"
                            className={`${styles.btn} ${styles.danger}`}
                            disabled={busy}
                            onClick={() => setConfirming(true)}
                        >
                            Elimina
                        </button>
                    )}
                </div>
            </div>

            <p className={styles.help}>{skill.description}</p>

            <dl className={styles.facts}>
                <dt>Fonte</dt>
                <dd className={styles.mono}>{sourceLabel(skill.source)}</dd>
                <dt>Impronta</dt>
                <dd className={styles.mono}>{skill.sha256.slice(0, 16)}…</dd>
                <dt>Dimensione</dt>
                <dd className={styles.mono}>{skill.chars} caratteri</dd>
            </dl>

            {skill.warnings.length > 0 ? (
                <div className={styles.stack} style={{ gap: 6 }} role="list" aria-label="Da controllare">
                    {skill.warnings.map((code) => (
                        <div key={code} role="listitem" className={styles.issue} data-tone="warn">
                            <span className={styles.warn}>da controllare</span>
                            <span>{WARNING_TEXT[code] ?? code}</span>
                        </div>
                    ))}
                </div>
            ) : (
                <p className={styles.muted}>Nessun segnale sospetto trovato nel testo. Leggilo comunque.</p>
            )}

            {!skill.enabled && (
                <p className={styles.warn}>
                    Leggi il testo prima di accenderla. Accesa, l&apos;agente la legge quando un compito le somiglia; le
                    sue istruzioni contano come contenuto esterno: non danno permessi e, dopo averle lette, ogni azione
                    a rischio alto chiede la tua approvazione.
                </p>
            )}

            <pre className={styles.pre} aria-label="Testo della skill">
                {skill.content}
            </pre>
        </section>
    );
}

export default function SkillsPage() {
    const [skills, setSkills] = useState<ImportedSkill[] | null>(null);
    const [selected, setSelected] = useState<ImportedSkillDetail | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [mode, setMode] = useState<"url" | "file">("url");
    const [url, setUrl] = useState("");
    const [file, setFile] = useState<File | null>(null);
    const [busy, setBusy] = useState(false);
    const [note, setNote] = useState<string | null>(null);
    const [importError, setImportError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        try {
            const result = await getJson<{ skills: ImportedSkill[] }>("/api/skills");
            setSkills(result.skills);
            setError(null);
        } catch (err) {
            setError(message(err));
        }
    }, []);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    const open = async (id: string) => {
        try {
            setSelected(await getJson<ImportedSkillDetail>(`/api/skills/${encodeURIComponent(id)}`));
            setNote(null);
        } catch (err) {
            setNote(message(err));
        }
    };

    const submit = async (event: React.FormEvent) => {
        event.preventDefault();
        setBusy(true);
        setImportError(null);
        setNote(null);
        try {
            const body =
                mode === "url"
                    ? { url: url.trim() }
                    : { content: file ? await readText(file) : "", filename: file?.name ?? "SKILL.md" };
            const imported = await postJson<ImportedSkillDetail>("/api/skills/import", body);
            setSelected(imported);
            setUrl("");
            setFile(null);
            setNote(
                !imported.replaced
                    ? `${imported.name} importata, spenta: leggila qui sotto.`
                    : imported.changed
                      ? `${imported.name} aggiornata: il testo è cambiato, rileggilo prima di accenderla.`
                      : `${imported.name}: stesso testo di prima, niente è cambiato.`,
            );
            await refresh();
        } catch (err) {
            setImportError(importErrorText(message(err)));
        } finally {
            setBusy(false);
        }
    };

    const toggle = async (enabled: boolean) => {
        if (!selected) {
            return;
        }
        setBusy(true);
        try {
            const updated = await putJson<ImportedSkill>(`/api/skills/${encodeURIComponent(selected.id)}`, { enabled });
            setSelected({ ...selected, ...updated });
            setNote(enabled ? `${updated.name} accesa: vale dalla prossima run.` : `${updated.name} spenta.`);
            await refresh();
        } catch (err) {
            setNote(message(err));
        } finally {
            setBusy(false);
        }
    };

    const remove = async () => {
        if (!selected) {
            return;
        }
        setBusy(true);
        try {
            await deleteJson(`/api/skills/${encodeURIComponent(selected.id)}`);
            setNote(`${selected.name} eliminata.`);
            setSelected(null);
            await refresh();
        } catch (err) {
            setNote(message(err));
        } finally {
            setBusy(false);
        }
    };

    const ready = mode === "url" ? url.trim().startsWith("https://") : file !== null;
    const enabled = skills?.filter((skill) => skill.enabled).length ?? 0;

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>SKILL</h1>
                {skills && (
                    <span className={styles.badge} data-tone={enabled ? "ok" : undefined}>
                        {enabled} accese su {skills.length}
                    </span>
                )}
                {note && (
                    <span className={styles.muted} role="status">
                        {note}
                    </span>
                )}
            </div>

            <form className={styles.card} onSubmit={submit} aria-label="Importa una skill">
                <h2 className={styles.h2}>Importa una skill</h2>
                <p className={styles.help}>
                    Formato SKILL.md, lo stesso di Claude Code, Codex e OpenClaw. Si importa solo il testo: script e
                    altri file della skill restano fuori e niente viene eseguito. Nel 2026 i registri di skill hanno
                    avuto skill malevole: importa da fonti che conosci e leggi il testo prima di accenderla.
                </p>
                <div className={styles.row} role="radiogroup" aria-label="Da dove">
                    <label className={styles.check}>
                        <input type="radio" name="mode" checked={mode === "url"} onChange={() => setMode("url")} />
                        da un link
                    </label>
                    <label className={styles.check}>
                        <input type="radio" name="mode" checked={mode === "file"} onChange={() => setMode("file")} />
                        da un file
                    </label>
                </div>
                <div className={styles.filters}>
                    {mode === "url" ? (
                        <label className={`${styles.field} ${styles.grow}`}>
                            Link https al file o alla cartella su GitHub
                            <input
                                value={url}
                                placeholder="https://github.com/…/skills/nome/SKILL.md"
                                spellCheck={false}
                                onChange={(event) => setUrl(event.target.value)}
                            />
                        </label>
                    ) : (
                        <label className={`${styles.field} ${styles.grow}`}>
                            File SKILL.md
                            <input
                                type="file"
                                accept=".md,text/markdown,text/plain"
                                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                            />
                        </label>
                    )}
                    <button type="submit" className={`${styles.btn} ${styles.go}`} disabled={busy || !ready}>
                        {busy ? "Importo…" : "Importa"}
                    </button>
                </div>
                {importError && (
                    <p className={styles.error} role="alert">
                        {importError}
                    </p>
                )}
            </form>

            {error && <p className={styles.error}>Skill non disponibili: {error}</p>}

            {skills && (
                <div className={styles.skills}>
                    <section className={styles.section} aria-label="Skill importate">
                        <h2 className={styles.h2}>
                            Importate <span>{skills.length}</span>
                        </h2>
                        {skills.length ? (
                            <ul className={styles.plain} style={{ display: "grid", gap: 8 }}>
                                {skills.map((skill) => (
                                    <li key={skill.id}>
                                        <button
                                            type="button"
                                            className={styles.skillItem}
                                            aria-current={selected?.id === skill.id ? "true" : undefined}
                                            onClick={() => open(skill.id)}
                                        >
                                            <span className={styles.row}>
                                                <span className={styles.mono}>{skill.name}</span>
                                                <StateBadge skill={skill} />
                                                {skill.warnings.length > 0 && (
                                                    <span className={styles.badge} data-tone="warn">
                                                        {skill.warnings.length} da controllare
                                                    </span>
                                                )}
                                            </span>
                                            <span className={styles.help}>{skill.description}</span>
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        ) : (
                            <p className={styles.muted}>Nessuna skill importata.</p>
                        )}
                    </section>

                    {selected ? (
                        <SkillDetail
                            key={selected.id}
                            skill={selected}
                            busy={busy}
                            onToggle={toggle}
                            onDelete={remove}
                        />
                    ) : (
                        skills.length > 0 && <p className={styles.muted}>Scegli una skill per leggerla.</p>
                    )}
                </div>
            )}
        </main>
    );
}
