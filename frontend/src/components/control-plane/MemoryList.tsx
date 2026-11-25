/**
 * @file frontend/src/components/control-plane/MemoryList.tsx
 * @description The memories of the user (M11, rewritten in F6): kind,
 * source and trust of each, edited in place, vouched for, or forgotten.
 *
 * An untrusted memory was written while a run held content from the web,
 * files or MCP: it is recalled as data, never as an instruction. "I trust it"
 * makes it the user's own, so a preference or rule reaches every run; the
 * backend checks the text and writes the change to the audit first.
 */
import React, { useState } from "react";

import { TrustBadge } from "@/components/control-plane/RunDetailView";
import styles from "@/components/control-plane/control.module.css";
import type { Memory, MemoryChanges, MemoryKind } from "@/lib/api/memory";
import { catalog, localeOf, useLanguage, type Lang } from "@/lib/i18n";
import { KIND_TEXT, kindLabel, sourceText } from "@/lib/nucleo/memory";

const TEXT = catalog({
    en: {
        memoryText: "Text of the memory",
        kind: "Kind",
        save: "Save",
        cancel: "Cancel",
        edit: "Edit",
        trustTitle: "It becomes your memory: if it is a preference or a rule, it goes into every run.",
        trust: "I trust it",
        confirmForget: "Confirm: forget",
        forgetLabel: (kind: string, id: string) => `Forget ${kind} ${id}`,
        forget: "Forget",
        none: "No memories here.",
    },
    it: {
        memoryText: "Testo del ricordo",
        kind: "Tipo",
        save: "Salva",
        cancel: "Annulla",
        edit: "Modifica",
        trustTitle: "Diventa un tuo ricordo: se è una preferenza o una regola, entra in ogni run.",
        trust: "Mi fido",
        confirmForget: "Conferma: dimentica",
        forgetLabel: (kind: string, id: string) => `Dimentica ${kind} ${id}`,
        forget: "Dimentica",
        none: "Nessun ricordo qui.",
    },
});

const EDIT_KINDS: MemoryKind[] = ["fact", "preference", "rule", "episode"];

function date(value: string | null, lang: Lang): string {
    if (!value) {
        return "";
    }
    const parsed = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
    return Number.isNaN(parsed.getTime())
        ? value
        : parsed.toLocaleString(localeOf(lang), { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function MemoryItem({
    memory,
    busy,
    onSave,
    onForget,
}: {
    memory: Memory;
    busy: boolean;
    onSave: (memory: Memory, changes: MemoryChanges) => Promise<boolean>;
    onForget: (memory: Memory) => void;
}) {
    const lang = useLanguage();
    const t = TEXT[lang];
    const [editing, setEditing] = useState(false);
    const [text, setText] = useState(memory.content);
    const [kind, setKind] = useState<MemoryKind>(memory.kind as MemoryKind);
    const [confirming, setConfirming] = useState(false);

    const save = async () => {
        const changes: MemoryChanges = {};
        if (text.trim() !== memory.content) {
            changes.content = text.trim();
        }
        if (kind !== memory.kind) {
            changes.kind = kind;
        }
        if (Object.keys(changes).length === 0 || (await onSave(memory, changes))) {
            setEditing(false);
        }
    };

    return (
        <li className={styles.memory} data-trusted={memory.trusted}>
            <div className={styles.row}>
                <span className={styles.badge}>{kindLabel(memory.kind, lang)}</span>
                <TrustBadge trusted={memory.trusted} />
                <span className={styles.source}>
                    {[sourceText(memory.source, lang), date(memory.created_at, lang)].filter(Boolean).join(" · ")}
                </span>
            </div>

            {editing ? (
                <div className={styles.stack} style={{ gap: 8 }}>
                    <textarea
                        className={styles.input}
                        value={text}
                        rows={3}
                        maxLength={1200}
                        aria-label={t.memoryText}
                        onChange={(event) => setText(event.target.value)}
                    />
                    <div className={styles.row}>
                        <label className={styles.field}>
                            {t.kind}
                            <select value={kind} onChange={(event) => setKind(event.target.value as MemoryKind)}>
                                {EDIT_KINDS.map((item) => (
                                    <option key={item} value={item}>
                                        {KIND_TEXT[lang][item].label}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <button
                            type="button"
                            className={`${styles.btn} ${styles.go}`}
                            disabled={busy || !text.trim()}
                            onClick={save}
                        >
                            {t.save}
                        </button>
                        <button
                            type="button"
                            className={styles.btn}
                            onClick={() => {
                                setEditing(false);
                                setText(memory.content);
                                setKind(memory.kind as MemoryKind);
                            }}
                        >
                            {t.cancel}
                        </button>
                    </div>
                </div>
            ) : (
                <p className={styles.memoryText}>{memory.content}</p>
            )}

            {!editing && (
                <div className={styles.row}>
                    <button type="button" className={styles.linkBtn} disabled={busy} onClick={() => setEditing(true)}>
                        {t.edit}
                    </button>
                    {!memory.trusted && (
                        <button
                            type="button"
                            className={styles.linkBtn}
                            disabled={busy}
                            title={t.trustTitle}
                            onClick={() => void onSave(memory, { trusted: true })}
                        >
                            {t.trust}
                        </button>
                    )}
                    {confirming ? (
                        <>
                            <button
                                type="button"
                                className={`${styles.btn} ${styles.danger}`}
                                disabled={busy}
                                onClick={() => onForget(memory)}
                            >
                                {t.confirmForget}
                            </button>
                            <button type="button" className={styles.linkBtn} onClick={() => setConfirming(false)}>
                                {t.cancel}
                            </button>
                        </>
                    ) : (
                        <button
                            type="button"
                            className={styles.linkBtn}
                            disabled={busy}
                            aria-label={t.forgetLabel(kindLabel(memory.kind, lang), memory.id)}
                            onClick={() => setConfirming(true)}
                        >
                            {t.forget}
                        </button>
                    )}
                </div>
            )}
        </li>
    );
}

export default function MemoryList({
    memories,
    busy = false,
    onSave,
    onForget,
}: {
    memories: Memory[];
    busy?: boolean;
    onSave: (memory: Memory, changes: MemoryChanges) => Promise<boolean>;
    onForget: (memory: Memory) => void;
}) {
    const lang = useLanguage();
    if (memories.length === 0) {
        return <p className={styles.muted}>{TEXT[lang].none}</p>;
    }

    return (
        <ul className={styles.plain} style={{ display: "grid", gap: 10 }}>
            {memories.map((memory) => (
                <MemoryItem key={`${memory.id}-${memory.content}-${memory.kind}-${memory.trusted}`} memory={memory} busy={busy} onSave={onSave} onForget={onForget} />
            ))}
        </ul>
    );
}
