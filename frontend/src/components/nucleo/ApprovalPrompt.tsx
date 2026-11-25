/**
 * @file frontend/src/components/nucleo/ApprovalPrompt.tsx
 * @description The oldest pending approval, decided from the Nucleo: the
 * exact call, its arguments and the time left. The others wait their turn
 * (the Approvals page lists them all).
 */
"use client";

import Link from "next/link";
import React, { useEffect, useState } from "react";

import { type ApprovalRequest, type Decision, secondsLeft } from "@/components/control-plane/ApprovalCard";

import styles from "./nucleo.module.css";

/** `key: value` per line; nested values stay JSON. Short enough to read at a glance. */
export function formatArguments(args: Record<string, unknown>): string {
    return Object.entries(args)
        .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
        .join("\n");
}

export default function ApprovalPrompt({
    pending,
    busy,
    onDecide,
}: {
    pending: ApprovalRequest[];
    busy: boolean;
    onDecide: (id: string, decision: Decision) => void;
}) {
    const [now, setNow] = useState(() => Date.now());

    useEffect(() => {
        const timer = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(timer);
    }, []);

    const item = pending[0];
    if (!item) {
        return null;
    }

    const remaining = secondsLeft(item.expires_at, now);
    const disabled = busy || remaining === 0;

    return (
        <div className={`${styles.approval} rise`} role="dialog" aria-label={`Approvazione per ${item.tool}`}>
            <div className={styles.approvalTitle}>APPROVAZIONE RICHIESTA · {item.risk.toUpperCase()}</div>
            <div className={styles.approvalWhat}>{item.tool}</div>
            {item.arguments ? (
                <pre>{formatArguments(item.arguments)}</pre>
            ) : (
                <div className={styles.approvalWhy}>
                    Argomenti non disponibili: apri la run prima di consentire.
                </div>
            )}
            <div className={styles.approvalWhy}>
                {remaining > 0 ? `Il motore aspetta la tua decisione · scade tra ${remaining}s` : "Scaduta"}
            </div>
            <div className={styles.row}>
                <button
                    type="button"
                    className={`${styles.btn} ${styles.go}`}
                    disabled={disabled}
                    onClick={() => onDecide(item.id, "allow")}
                >
                    Consenti
                </button>
                <button type="button" className={styles.btn} disabled={disabled} onClick={() => onDecide(item.id, "deny")}>
                    Nega
                </button>
                {pending.length > 1 && (
                    <Link className={styles.more} href="/control-plane/approvals">
                        +{pending.length - 1} in attesa
                    </Link>
                )}
            </div>
        </div>
    );
}
