/**
 * @file frontend/src/components/control-plane/MemoryList.tsx
 * @description The memories of the user (M11, rewritten in F6): kind,
 * source and trust of each, edited in place, vouched for, or forgotten.
 *
 * An untrusted memory was written while a run held content from the web,
 * files or MCP: it is recalled as data, never as an instruction. "Mi fido"
 * makes it the user's own, so a preference or rule reaches every run; the
 * backend checks the text and writes the change to the audit first.
 */
import React, { useState } from "react";

import { TrustBadge } from "@/components/control-plane/RunDetailView";
import styles from "@/components/control-plane/control.module.css";
import type { Memory, MemoryChanges, MemoryKind } from "@/lib/api/memory";
import { KIND_TEXT, kindLabel, sourceText } from "@/lib/nucleo/memory";

const EDIT_KINDS: MemoryKind[] = ["fact", "preference", "rule", "episode"];

function date(value: string | null): string {
    if (!value) {
        return "";
    }
    const parsed = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
    return Number.isNaN(parsed.getTime())
        ? value
        : parsed.toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
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
                <span className={styles.badge}>{kindLabel(memory.kind)}</span>
                <TrustBadge trusted={memory.trusted} />
                <span className={styles.source}>
                    {[sourceText(memory.source), date(memory.created_at)].filter(Boolean).join(" · ")}
                </span>
            </div>

            {editing ? (
                <div className={styles.stack} style={{ gap: 8 }}>
                    <textarea
                        className={styles.input}
                        value={text}
                        rows={3}
                        maxLength={1200}
                        aria-label="Testo del ricordo"
                        onChange={(event) => setText(event.target.value)}
                    />
                    <div className={styles.row}>
                        <label className={styles.field}>
                            Tipo
                            <select value={kind} onChange={(event) => setKind(event.target.value as MemoryKind)}>
                                {EDIT_KINDS.map((item) => (
                                    <option key={item} value={item}>
                                        {KIND_TEXT[item].label}
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
                            Salva
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
                            Annulla
                        </button>
                    </div>
                </div>
            ) : (
                <p className={styles.memoryText}>{memory.content}</p>
            )}

            {!editing && (
                <div className={styles.row}>
                    <button type="button" className={styles.linkBtn} disabled={busy} onClick={() => setEditing(true)}>
                        Modifica
                    </button>
                    {!memory.trusted && (
                        <button
                            type="button"
                            className={styles.linkBtn}
                            disabled={busy}
                            title="Diventa un tuo ricordo: se è una preferenza o una regola, entra in ogni run."
                            onClick={() => void onSave(memory, { trusted: true })}
                        >
                            Mi fido
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
                                Conferma: dimentica
                            </button>
                            <button type="button" className={styles.linkBtn} onClick={() => setConfirming(false)}>
                                Annulla
                            </button>
                        </>
                    ) : (
                        <button
                            type="button"
                            className={styles.linkBtn}
                            disabled={busy}
                            aria-label={`Dimentica ${kindLabel(memory.kind)} ${memory.id}`}
                            onClick={() => setConfirming(true)}
                        >
                            Dimentica
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
    if (memories.length === 0) {
        return <p className={styles.muted}>Nessun ricordo qui.</p>;
    }

    return (
        <ul className={styles.plain} style={{ display: "grid", gap: 10 }}>
            {memories.map((memory) => (
                <MemoryItem key={`${memory.id}-${memory.content}-${memory.kind}-${memory.trusted}`} memory={memory} busy={busy} onSave={onSave} onForget={onForget} />
            ))}
        </ul>
    );
}
