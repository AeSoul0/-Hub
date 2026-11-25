/**
 * @file frontend/src/app/control-plane/skills/page.tsx
 * @description Skills (F5, ADR-026): import a skill in the SKILL.md format
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
import { catalog, useLanguage, useText } from "@/lib/i18n";
import { WARNING_TEXT, importErrorText, sourceLabel } from "@/lib/nucleo/tools";

const TEXT = catalog({
    en: {
        on: "on",
        off: "off",
        turnOff: "Turn off",
        turnOn: "Turn on",
        confirmDelete: "Confirm: delete",
        cancel: "Cancel",
        delete: "Delete",
        source: "Source",
        fingerprint: "Fingerprint",
        size: "Size",
        chars: (count: number) => `${count} characters`,
        toCheck: "to check",
        toCheckList: "To check",
        clean: "No suspicious sign found in the text. Read it anyway.",
        readFirst:
            "Read the text before turning it on. Once on, the agent reads it when a task resembles it; its instructions count as external content: they grant no permission and, after reading them, every high-risk action asks for your approval.",
        skillText: "Text of the skill",
        imported: (name: string) => `${name} imported, off: read it below.`,
        updated: (name: string) => `${name} updated: the text changed, read it again before turning it on.`,
        same: (name: string) => `${name}: same text as before, nothing changed.`,
        turnedOn: (name: string) => `${name} on: it applies from the next run.`,
        turnedOff: (name: string) => `${name} off.`,
        deleted: (name: string) => `${name} deleted.`,
        title: "SKILLS",
        count: (on: number, total: number) => `${on} of ${total} on`,
        importSkill: "Import a skill",
        importHelp:
            "SKILL.md format, the same as Claude Code, Codex and OpenClaw. Only the text is imported: scripts and other files of the skill stay out and nothing runs. In 2026 skill registries had malicious skills: import from sources you know and read the text before turning it on.",
        from: "From where",
        fromLink: "from a link",
        fromFile: "from a file",
        link: "https link to the file or the folder on GitHub",
        file: "SKILL.md file",
        importing: "Importing…",
        import: "Import",
        unavailable: "Skills not available:",
        importedSkills: "Imported skills",
        importedTitle: "Imported",
        warnings: (count: number) => `${count} to check`,
        none: "No skill imported.",
        choose: "Choose a skill to read it.",
    },
    it: {
        on: "accesa",
        off: "spenta",
        turnOff: "Spegni",
        turnOn: "Accendi",
        confirmDelete: "Conferma: elimina",
        cancel: "Annulla",
        delete: "Elimina",
        source: "Fonte",
        fingerprint: "Impronta",
        size: "Dimensione",
        chars: (count: number) => `${count} caratteri`,
        toCheck: "da controllare",
        toCheckList: "Da controllare",
        clean: "Nessun segnale sospetto trovato nel testo. Leggilo comunque.",
        readFirst:
            "Leggi il testo prima di accenderla. Accesa, l'agente la legge quando un compito le somiglia; le sue istruzioni contano come contenuto esterno: non danno permessi e, dopo averle lette, ogni azione a rischio alto chiede la tua approvazione.",
        skillText: "Testo della skill",
        imported: (name: string) => `${name} importata, spenta: leggila qui sotto.`,
        updated: (name: string) => `${name} aggiornata: il testo è cambiato, rileggilo prima di accenderla.`,
        same: (name: string) => `${name}: stesso testo di prima, niente è cambiato.`,
        turnedOn: (name: string) => `${name} accesa: vale dalla prossima run.`,
        turnedOff: (name: string) => `${name} spenta.`,
        deleted: (name: string) => `${name} eliminata.`,
        title: "SKILL",
        count: (on: number, total: number) => `${on} accese su ${total}`,
        importSkill: "Importa una skill",
        importHelp:
            "Formato SKILL.md, lo stesso di Claude Code, Codex e OpenClaw. Si importa solo il testo: script e altri file della skill restano fuori e niente viene eseguito. Nel 2026 i registri di skill hanno avuto skill malevole: importa da fonti che conosci e leggi il testo prima di accenderla.",
        from: "Da dove",
        fromLink: "da un link",
        fromFile: "da un file",
        link: "Link https al file o alla cartella su GitHub",
        file: "File SKILL.md",
        importing: "Importo…",
        import: "Importa",
        unavailable: "Skill non disponibili:",
        importedSkills: "Skill importate",
        importedTitle: "Importate",
        warnings: (count: number) => `${count} da controllare`,
        none: "Nessuna skill importata.",
        choose: "Scegli una skill per leggerla.",
    },
});

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
    const t = useText(TEXT);
    return skill.enabled ? (
        <span className={styles.badge} data-tone="ok">
            {t.on}
        </span>
    ) : (
        <span className={styles.badge}>{t.off}</span>
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
    const lang = useLanguage();
    const t = TEXT[lang];
    const [confirming, setConfirming] = useState(false);

    return (
        <section className={styles.card} aria-label={`Skill ${skill.name}`}>
            <div className={styles.head}>
                <h2 className={styles.runTitle}>{skill.name}</h2>
                <StateBadge skill={skill} />
                <div className={styles.headEnd}>
                    {skill.enabled ? (
                        <button type="button" className={styles.btn} disabled={busy} onClick={() => onToggle(false)}>
                            {t.turnOff}
                        </button>
                    ) : (
                        <button
                            type="button"
                            className={`${styles.btn} ${styles.go}`}
                            disabled={busy}
                            onClick={() => onToggle(true)}
                        >
                            {t.turnOn}
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
                                {t.confirmDelete}
                            </button>
                            <button type="button" className={styles.btn} onClick={() => setConfirming(false)}>
                                {t.cancel}
                            </button>
                        </>
                    ) : (
                        <button
                            type="button"
                            className={`${styles.btn} ${styles.danger}`}
                            disabled={busy}
                            onClick={() => setConfirming(true)}
                        >
                            {t.delete}
                        </button>
                    )}
                </div>
            </div>

            <p className={styles.help}>{skill.description}</p>

            <dl className={styles.facts}>
                <dt>{t.source}</dt>
                <dd className={styles.mono}>{sourceLabel(skill.source)}</dd>
                <dt>{t.fingerprint}</dt>
                <dd className={styles.mono}>{skill.sha256.slice(0, 16)}…</dd>
                <dt>{t.size}</dt>
                <dd className={styles.mono}>{t.chars(skill.chars)}</dd>
            </dl>

            {skill.warnings.length > 0 ? (
                <div className={styles.stack} style={{ gap: 6 }} role="list" aria-label={t.toCheckList}>
                    {skill.warnings.map((code) => (
                        <div key={code} role="listitem" className={styles.issue} data-tone="warn">
                            <span className={styles.warn}>{t.toCheck}</span>
                            <span>{WARNING_TEXT[lang][code] ?? code}</span>
                        </div>
                    ))}
                </div>
            ) : (
                <p className={styles.muted}>{t.clean}</p>
            )}

            {!skill.enabled && (
                <p className={styles.warn}>{t.readFirst}</p>
            )}

            <pre className={styles.pre} aria-label={t.skillText}>
                {skill.content}
            </pre>
        </section>
    );
}

export default function SkillsPage() {
    const lang = useLanguage();
    const t = TEXT[lang];
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
                    ? t.imported(imported.name)
                    : imported.changed
                      ? t.updated(imported.name)
                      : t.same(imported.name),
            );
            await refresh();
        } catch (err) {
            setImportError(importErrorText(message(err), lang));
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
            setNote(enabled ? t.turnedOn(updated.name) : t.turnedOff(updated.name));
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
            setNote(t.deleted(selected.name));
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
                <h1 className={styles.title}>{t.title}</h1>
                {skills && (
                    <span className={styles.badge} data-tone={enabled ? "ok" : undefined}>
                        {t.count(enabled, skills.length)}
                    </span>
                )}
                {note && (
                    <span className={styles.muted} role="status">
                        {note}
                    </span>
                )}
            </div>

            <form className={styles.card} onSubmit={submit} aria-label={t.importSkill}>
                <h2 className={styles.h2}>{t.importSkill}</h2>
                <p className={styles.help}>{t.importHelp}</p>
                <div className={styles.row} role="radiogroup" aria-label={t.from}>
                    <label className={styles.check}>
                        <input type="radio" name="mode" checked={mode === "url"} onChange={() => setMode("url")} />
                        {t.fromLink}
                    </label>
                    <label className={styles.check}>
                        <input type="radio" name="mode" checked={mode === "file"} onChange={() => setMode("file")} />
                        {t.fromFile}
                    </label>
                </div>
                <div className={styles.filters}>
                    {mode === "url" ? (
                        <label className={`${styles.field} ${styles.grow}`}>
                            {t.link}
                            <input
                                value={url}
                                placeholder="https://github.com/…/skills/name/SKILL.md"
                                spellCheck={false}
                                onChange={(event) => setUrl(event.target.value)}
                            />
                        </label>
                    ) : (
                        <label className={`${styles.field} ${styles.grow}`}>
                            {t.file}
                            <input
                                type="file"
                                accept=".md,text/markdown,text/plain"
                                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                            />
                        </label>
                    )}
                    <button type="submit" className={`${styles.btn} ${styles.go}`} disabled={busy || !ready}>
                        {busy ? t.importing : t.import}
                    </button>
                </div>
                {importError && (
                    <p className={styles.error} role="alert">
                        {importError}
                    </p>
                )}
            </form>

            {error && <p className={styles.error}>
                    {t.unavailable} {error}
                </p>}

            {skills && (
                <div className={styles.skills}>
                    <section className={styles.section} aria-label={t.importedSkills}>
                        <h2 className={styles.h2}>
                            {t.importedTitle} <span>{skills.length}</span>
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
                                                        {t.warnings(skill.warnings.length)}
                                                    </span>
                                                )}
                                            </span>
                                            <span className={styles.help}>{skill.description}</span>
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        ) : (
                            <p className={styles.muted}>{t.none}</p>
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
                        skills.length > 0 && <p className={styles.muted}>{t.choose}</p>
                    )}
                </div>
            )}
        </main>
    );
}
