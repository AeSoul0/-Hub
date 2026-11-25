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
import { catalog, useLanguage } from "@/lib/i18n";

const TEXT = catalog({
    en: {
        approvalFor: (tool: string) => `Approval for ${tool}`,
        title: "APPROVAL REQUESTED",
        noArguments: "Arguments not available: open the run before allowing.",
        waiting: (seconds: number) => `The engine is waiting for your decision · expires in ${seconds}s`,
        expired: "Expired",
        allow: "Allow",
        deny: "Deny",
        more: (count: number) => `+${count} waiting`,
    },
    it: {
        approvalFor: (tool: string) => `Approvazione per ${tool}`,
        title: "APPROVAZIONE RICHIESTA",
        noArguments: "Argomenti non disponibili: apri la run prima di consentire.",
        waiting: (seconds: number) => `Il motore aspetta la tua decisione · scade tra ${seconds}s`,
        expired: "Scaduta",
        allow: "Consenti",
        deny: "Nega",
        more: (count: number) => `+${count} in attesa`,
    },
});

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
    const lang = useLanguage();
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
    const t = TEXT[lang];
    const disabled = busy || remaining === 0;

    return (
        <div className={`${styles.approval} rise`} role="dialog" aria-label={t.approvalFor(item.tool)}>
            <div className={styles.approvalTitle}>
                {t.title} · {item.risk.toUpperCase()}
            </div>
            <div className={styles.approvalWhat}>{item.tool}</div>
            {item.arguments ? (
                <pre>{formatArguments(item.arguments)}</pre>
            ) : (
                <div className={styles.approvalWhy}>{t.noArguments}</div>
            )}
            <div className={styles.approvalWhy}>
                {remaining > 0 ? t.waiting(remaining) : t.expired}
            </div>
            <div className={styles.row}>
                <button
                    type="button"
                    className={`${styles.btn} ${styles.go}`}
                    disabled={disabled}
                    onClick={() => onDecide(item.id, "allow")}
                >
                    {t.allow}
                </button>
                <button type="button" className={styles.btn} disabled={disabled} onClick={() => onDecide(item.id, "deny")}>
                    {t.deny}
                </button>
                {pending.length > 1 && (
                    <Link className={styles.more} href="/control-plane/approvals">
                        {t.more(pending.length - 1)}
                    </Link>
                )}
            </div>
        </div>
    );
}
