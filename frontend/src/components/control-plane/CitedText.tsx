/**
 * @file frontend/src/components/control-plane/CitedText.tsx
 * @description An answer with its document citations (F6). Each
 * [doc: path#L12-30] becomes a chip; a click opens the indexed passage it
 * points to (GET /api/documents/passage), so the user can check the source
 * without leaving the page. A citation that is not in the index says so.
 */
"use client";

import React, { useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import { getJson } from "@/lib/api/client";
import { locatorLabel, splitCitations, type Passage } from "@/lib/api/memory";
import { errorText } from "@/lib/nucleo/memory";

type Open = { key: string; passage?: Passage; error?: string };

export default function CitedText({ text, className }: { text: string; className?: string }) {
    const [open, setOpen] = useState<Open | null>(null);
    const parts = splitCitations(text);

    if (parts.every((part) => typeof part === "string")) {
        return <span className={className}>{text}</span>;
    }

    const show = async (key: string, path: string, locator: string) => {
        if (open?.key === key) {
            setOpen(null);
            return;
        }
        setOpen({ key });
        try {
            const passage = await getJson<Passage>("/api/documents/passage", { params: { path, locator } });
            setOpen({ key, passage });
        } catch (err) {
            setOpen({ key, error: errorText(err instanceof Error ? err.message : String(err)) });
        }
    };

    return (
        <span className={className}>
            {parts.map((part, index) => {
                if (typeof part === "string") {
                    return <React.Fragment key={index}>{part}</React.Fragment>;
                }
                const key = `${index}:${part.citation}`;
                return (
                    <button
                        key={key}
                        type="button"
                        className={styles.cite}
                        aria-expanded={open?.key === key}
                        title={`${part.path}, ${locatorLabel(part.locator)}`}
                        onClick={() => void show(key, part.path, part.locator)}
                    >
                        {part.path.split("/").pop()} · {locatorLabel(part.locator)}
                    </button>
                );
            })}
            {open && (
                <span className={styles.passage} role="note" aria-label="Passaggio citato">
                    {open.passage ? (
                        <>
                            <span className={styles.sub}>
                                {open.passage.path} · {locatorLabel(open.passage.locator)}
                            </span>
                            {open.passage.content}
                        </>
                    ) : open.error ? (
                        <span className={styles.error}>{open.error}</span>
                    ) : (
                        <span className={styles.muted}>Carico il passaggio…</span>
                    )}
                </span>
            )}
        </span>
    );
}
