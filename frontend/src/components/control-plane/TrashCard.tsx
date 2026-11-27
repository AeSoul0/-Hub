/**
 * @file frontend/src/components/control-plane/TrashCard.tsx
 * @description ÆHub's trash on the STRUMENTI page (N5): what delete_path
 * removed, restorable for AEHUB_TRASH_DAYS days. Restore puts an item back
 * where it was (never over a file that is there now); the owner can also
 * remove one for good or empty the trash.
 */
"use client";

import React, { useCallback, useEffect, useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import { deleteJson, getJson, postJson } from "@/lib/api/client";
import { catalog, useLanguage } from "@/lib/i18n";

export interface TrashItem {
    id: string;
    original: string;
    deleted_at: string;
    kind: "file" | "folder";
    size: number;
}

interface TrashView {
    days: number;
    items: TrashItem[];
}

const TEXT = catalog({
    en: {
        title: "Trash",
        help: (days: number) =>
            `What the agents delete comes here, out of their reach, and stays for ${days} days. Deleting by voice needs "yes, delete".`,
        empty: "The trash is empty.",
        restore: "Restore",
        remove: "Delete for good",
        emptyAll: "Empty the trash",
        confirmAll: "Click again to empty it",
        restored: (path: string) => `Restored: ${path}`,
        removed: "Deleted for good.",
        emptied: (count: number) => `${count} items deleted for good.`,
        failed: "Not done:",
        folder: "folder",
        deleted: (when: string) => `deleted ${when}`,
    },
    it: {
        title: "Cestino",
        help: (days: number) =>
            `Quello che gli agenti eliminano finisce qui, fuori dalla loro portata, e resta ${days} giorni. A voce per eliminare serve «sì, elimina».`,
        empty: "Il cestino è vuoto.",
        restore: "Ripristina",
        remove: "Elimina per sempre",
        emptyAll: "Svuota il cestino",
        confirmAll: "Clicca ancora per svuotarlo",
        restored: (path: string) => `Ripristinato: ${path}`,
        removed: "Eliminato per sempre.",
        emptied: (count: number) => `${count} elementi eliminati per sempre.`,
        failed: "Non fatto:",
        folder: "cartella",
        deleted: (when: string) => `eliminato ${when}`,
    },
});

function size(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function TrashCard() {
    const lang = useLanguage();
    const t = TEXT[lang];
    const [view, setView] = useState<TrashView | null>(null);
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const [confirm, setConfirm] = useState(false);

    const load = useCallback(async () => {
        try {
            setView(await getJson<TrashView>("/api/tools/trash"));
        } catch (error) {
            setNote(
                `${TEXT[lang].failed} ${error instanceof Error ? error.message : String(error)}`
            );
        }
    }, [lang]);

    useEffect(() => {
        const first = setTimeout(() => void load(), 0);
        return () => clearTimeout(first);
    }, [load]);

    const act = async (work: () => Promise<string>) => {
        setBusy(true);
        try {
            setNote(await work());
        } catch (error) {
            setNote(`${t.failed} ${error instanceof Error ? error.message : String(error)}`);
        } finally {
            setBusy(false);
            setConfirm(false);
            void load();
        }
    };

    const items = view?.items ?? [];
    return (
        <section className={styles.card} aria-label={t.title}>
            <h2 className={styles.h2}>{t.title}</h2>
            <p className={styles.help}>{t.help(view?.days ?? 30)}</p>
            {items.length === 0 ? (
                <p className={styles.help}>{t.empty}</p>
            ) : (
                <ul className={styles.lines} aria-label={t.title}>
                    {items.map((item) => (
                        <li key={item.id}>
                            <span className={styles.mono}>
                                {item.original}
                                {item.kind === "folder" ? ` (${t.folder})` : ""}
                            </span>
                            <b>
                                {size(item.size)} ·{" "}
                                {t.deleted(new Date(item.deleted_at).toLocaleString(lang))}
                            </b>
                            <span className={styles.row}>
                                <button
                                    type="button"
                                    className={`${styles.btn} ${styles.go}`}
                                    disabled={busy}
                                    onClick={() =>
                                        void act(async () => {
                                            const done = await postJson<{ restored: string }>(
                                                `/api/tools/trash/${encodeURIComponent(item.id)}/restore`,
                                                {}
                                            );
                                            return t.restored(done.restored);
                                        })
                                    }
                                >
                                    {t.restore}
                                </button>
                                <button
                                    type="button"
                                    className={styles.btn}
                                    disabled={busy}
                                    onClick={() =>
                                        void act(async () => {
                                            await deleteJson(
                                                `/api/tools/trash/${encodeURIComponent(item.id)}`
                                            );
                                            return t.removed;
                                        })
                                    }
                                >
                                    {t.remove}
                                </button>
                            </span>
                        </li>
                    ))}
                </ul>
            )}
            {items.length > 0 && (
                <button
                    type="button"
                    className={styles.btn}
                    disabled={busy}
                    onClick={() => {
                        if (!confirm) {
                            setConfirm(true);
                            return;
                        }
                        void act(async () =>
                            t.emptied(
                                (await deleteJson<{ removed: number }>("/api/tools/trash")).removed
                            )
                        );
                    }}
                >
                    {confirm ? t.confirmAll : t.emptyAll}
                </button>
            )}
            {note && (
                <p className={styles.help} role="status">
                    {note}
                </p>
            )}
        </section>
    );
}
