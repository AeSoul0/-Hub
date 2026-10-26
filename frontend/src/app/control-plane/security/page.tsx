/**
 * @file frontend/src/app/control-plane/security/page.tsx
 * @description Sicurezza (M11, restyled in F5): the audit trail of the
 * workspace, the integrity of its hash chain, and the provenance of what
 * the tools returned.
 *
 * GET /api/audit returns the latest tool calls recorded by the Tool Gateway
 * (who, which tool, risk, policy decision, outcome) and the Control Plane
 * changes (settings, imported skills), re-verifies the append-only hash
 * chain (a deleted or modified row shows up here) and says for each tool
 * whether its output is untrusted content. The list follows live run
 * events.
 */
"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useMemo, useState } from "react";

import LiveBadge from "@/components/control-plane/LiveBadge";
import type { AuditEntry } from "@/components/control-plane/RunDetailView";
import styles from "@/components/control-plane/control.module.css";
import { getJson } from "@/lib/api/client";
import { useLiveRefresh } from "@/lib/api/events";
import { ACTION_TEXT, DECISION_TEXT, RISK_LABELS } from "@/lib/nucleo/tools";
import { runHref } from "@/lib/routes";

type AuditRow = AuditEntry & { untrusted_output?: boolean | null };

interface AuditView {
    entries: AuditRow[];
    chain: {
        valid: boolean;
        checked: number;
        broken_at_seq: number | null;
        reason: string | null;
    };
}

// Decisions the Tool Gateway records (EXECUTING is written before the tool
// runs: audit is fail-closed).
const DECISIONS = ["", "ALLOW", "DENY", "EXECUTING", "CACHED", "ERROR", "CANCELLED"] as const;

function time(value: string | null): string {
    if (!value) {
        return "-";
    }
    const date = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
    return Number.isNaN(date.getTime())
        ? value
        : date.toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function SecurityPage() {
    const [view, setView] = useState<AuditView | null>(null);
    const [decision, setDecision] = useState<(typeof DECISIONS)[number]>("");
    const [tool, setTool] = useState("");
    const [externalOnly, setExternalOnly] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        const params: Record<string, string | number> = { limit: 200 };
        if (decision) {
            params.decision = decision;
        }
        if (tool) {
            params.tool = tool;
        }
        try {
            setView(await getJson<AuditView>("/api/audit", { params }));
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        }
    }, [decision, tool]);

    const live = useLiveRefresh(refresh, ["run.state", "run.resumed", "approval.decided"]);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    // The tool filter offers what the unfiltered list has shown so far.
    const [seenTools, setSeenTools] = useState<string[]>([]);
    useEffect(() => {
        if (view) {
            const update = setTimeout(
                () =>
                    setSeenTools((current) =>
                        [...new Set([...current, ...view.entries.map((entry) => entry.tool_name)])].sort(),
                    ),
                0,
            );
            return () => clearTimeout(update);
        }
    }, [view]);

    const entries = useMemo(
        () => (view?.entries ?? []).filter((entry) => !externalOnly || entry.untrusted_output === true),
        [view, externalOnly],
    );
    const chain = view?.chain;

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>SICUREZZA</h1>
                <LiveBadge state={live} />
            </div>

            {error && <p className={styles.error}>Audit non disponibile: {error}</p>}

            {chain && (
                <section className={`${styles.card} ${chain.valid ? "" : styles.amber}`} aria-label="Catena dell'audit">
                    <h2 className={styles.h2}>Catena dell&apos;audit</h2>
                    <p role="status" className={styles.row}>
                        <span className={styles.badge} data-tone={chain.valid ? "ok" : "bad"}>
                            {chain.valid ? "integra" : "rotta"}
                        </span>
                        <span className={chain.valid ? styles.muted : styles.error}>
                            {chain.valid
                                ? `${chain.checked} record verificati: nessuno è stato tolto o cambiato.`
                                : `Rotta al record ${chain.broken_at_seq}: ${chain.reason}. Qualcuno ha tolto o cambiato una riga.`}
                        </span>
                    </p>
                    <p className={styles.help}>
                        Ogni chiamata a un tool e ogni cambio dal Control Plane (impostazioni, skill) viene scritto
                        prima di avvenire, legato al precedente con un hash. Senza scrittura nell&apos;audit, niente
                        azione.
                    </p>
                </section>
            )}

            <section className={styles.card} aria-label="Provenienza">
                <h2 className={styles.h2}>Contenuti non affidabili</h2>
                <p className={styles.help}>
                    Pagine web, file, server MCP e skill importate sono contenuto esterno: possono contenere istruzioni
                    nascoste. Dopo averne letto uno, la run è segnata e ogni azione a rischio alto aspetta la tua
                    approvazione; lo stesso vale per i comandi dati a voce. La vista di ogni run dice se ha letto
                    contenuti esterni e quali tool ha potuto usare. Quali tool restituiscono contenuto esterno lo vedi in{" "}
                    <Link href="/control-plane/tools" className={styles.link}>
                        Strumenti
                    </Link>
                    .
                </p>
            </section>

            <section className={styles.section} aria-label="Registro">
                <h2 className={styles.h2}>
                    Registro <span>{entries.length}</span>
                </h2>
                <div className={styles.filters}>
                    <label className={styles.field}>
                        Decisione
                        <select
                            value={decision}
                            onChange={(event) => setDecision(event.target.value as (typeof DECISIONS)[number])}
                        >
                            {DECISIONS.map((item) => (
                                <option key={item} value={item}>
                                    {item ? (DECISION_TEXT[item]?.label ?? item) : "tutte"}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className={styles.field}>
                        Tool
                        <select value={tool} onChange={(event) => setTool(event.target.value)}>
                            <option value="">tutti</option>
                            {[...new Set([...seenTools, ...(tool ? [tool] : [])])].map((name) => (
                                <option key={name} value={name}>
                                    {ACTION_TEXT[name] ?? name}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className={styles.check}>
                        <input
                            type="checkbox"
                            checked={externalOnly}
                            onChange={(event) => setExternalOnly(event.target.checked)}
                        />
                        solo contenuto esterno
                    </label>
                </div>

                {view && entries.length === 0 ? (
                    <p className={styles.muted}>Nessuna voce nell&apos;audit.</p>
                ) : (
                    <div className={styles.tableWrap}>
                        <table className={styles.table}>
                            <thead>
                                <tr>
                                    <th>Ora</th>
                                    <th>Tool</th>
                                    <th>Rischio</th>
                                    <th>Decisione</th>
                                    <th>Esito</th>
                                    <th>Run</th>
                                </tr>
                            </thead>
                            <tbody>
                                {entries.map((entry) => {
                                    const risk = RISK_LABELS[entry.risk?.toLowerCase() as keyof typeof RISK_LABELS];
                                    const verdict = entry.decision ? DECISION_TEXT[entry.decision] : undefined;
                                    return (
                                        <tr key={entry.id}>
                                            <td className={styles.num}>{time(entry.timestamp)}</td>
                                            <td>
                                                <span className={styles.mono}>{ACTION_TEXT[entry.tool_name] ?? entry.tool_name}</span>
                                                {entry.untrusted_output && (
                                                    <span className={styles.sub}>restituisce contenuto esterno</span>
                                                )}
                                            </td>
                                            <td>
                                                {risk ? (
                                                    <span className={styles.badge} data-tone={risk.tone}>
                                                        {risk.label.replace("rischio ", "")}
                                                    </span>
                                                ) : (
                                                    entry.risk
                                                )}
                                            </td>
                                            <td>
                                                <span className={styles.badge} data-tone={verdict?.tone}>
                                                    {verdict?.label ?? entry.decision ?? "-"}
                                                </span>
                                            </td>
                                            <td className={`${styles.task} ${styles.outcome}`}>
                                                {entry.success ? (
                                                    <span className={styles.muted}>ok</span>
                                                ) : entry.decision === "EXECUTING" ? (
                                                    <span className={styles.muted}>scritto prima di eseguire</span>
                                                ) : (
                                                    <span className={styles.error}>{entry.error ?? "non riuscito"}</span>
                                                )}
                                            </td>
                                            <td className={styles.mono}>
                                                {entry.run_id ? (
                                                    <Link href={runHref(entry.run_id)} className={styles.link}>
                                                        {entry.run_id.slice(0, 16)}
                                                    </Link>
                                                ) : (
                                                    <span className={styles.faint}>Control Plane</span>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </section>
        </main>
    );
}
