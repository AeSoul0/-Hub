/**
 * @file frontend/src/components/control-plane/ApprovalCard.tsx
 * @description One pending approval: the exact call, its arguments, the
 * time left, and the two decisions.
 */
import Link from "next/link";
import React from "react";

import { runHref } from "@/lib/routes";

import styles from "./control.module.css";

export interface ApprovalRequest {
    id: string;
    run_id: string | null;
    session_id: string;
    tool: string;
    risk: string;
    arguments_hash: string;
    arguments?: Record<string, unknown> | null;
    requested_by: string;
    requested_at: string;
    expires_at: string;
}

export type Decision = "allow" | "deny";

// Backend timestamps are naive UTC.
export function secondsLeft(expiresAt: string, now: number): number {
    const expires = Date.parse(expiresAt.endsWith("Z") ? expiresAt : `${expiresAt}Z`);
    return Math.max(0, Math.round((expires - now) / 1000));
}

export default function ApprovalCard({
    item,
    now,
    busy,
    onDecide,
}: {
    item: ApprovalRequest;
    now: number;
    busy: boolean;
    onDecide: (id: string, decision: Decision) => void;
}) {
    const remaining = secondsLeft(item.expires_at, now);
    const disabled = busy || remaining === 0;
    const high = item.risk.toUpperCase() === "HIGH";

    return (
        <article className={`${styles.card} ${high ? styles.amber : ""}`} aria-label={`Approvazione per ${item.tool}`}>
            <div className={styles.row}>
                <span className={styles.mono}>{item.tool}</span>
                <span className={styles.badge} data-tone={high ? "warn" : undefined}>
                    {item.risk.toUpperCase()}
                </span>
                <span className={styles.muted}>{remaining > 0 ? `scade tra ${remaining} s` : "scaduta"}</span>
                {item.run_id && (
                    <Link href={runHref(item.run_id)} className={`${styles.link} ${styles.mono} ${styles.small}`} title={item.run_id}>
                        run {item.run_id.slice(0, 8)}
                    </Link>
                )}
            </div>

            {item.arguments ? (
                <pre className={styles.pre}>{JSON.stringify(item.arguments, null, 2)}</pre>
            ) : (
                <p className={styles.warn}>
                    Argomenti non disponibili (hash {item.arguments_hash.slice(0, 12)}…): apri la run prima di consentire.
                </p>
            )}

            <div className={styles.row}>
                <button type="button" onClick={() => onDecide(item.id, "allow")} disabled={disabled} className={`${styles.btn} ${styles.go}`}>
                    Consenti una volta
                </button>
                <button type="button" onClick={() => onDecide(item.id, "deny")} disabled={disabled} className={`${styles.btn} ${styles.danger}`}>
                    Nega
                </button>
            </div>
        </article>
    );
}
