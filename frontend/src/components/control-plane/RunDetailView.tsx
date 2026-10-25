/**
 * @file frontend/src/components/control-plane/RunDetailView.tsx
 * @description Presentation of one run as returned by GET /api/runs/{id},
 * in the Nucleo's style (F2).
 */
import Link from "next/link";
import React from "react";

import { EMPTY_USAGE, localTime, meters, savedStatus, toUsage, type RunLimits, type TrackedRun } from "@/lib/nucleo/runs";
import { runHref } from "@/lib/routes";

import RunMeters from "./RunMeters";
import styles from "./control.module.css";

export interface ToolCall {
    tool_call_id: string;
    tool_name: string;
    arguments: Record<string, unknown>;
    approval_id?: string | null;
}

export interface Observation {
    tool_call_id: string | null;
    tool_name: string | null;
    arguments: Record<string, unknown>;
    trusted: boolean;
    succeeded: boolean;
    modified_file: string | null;
    content: string;
}

export interface AuditEntry {
    id: string;
    timestamp: string | null;
    session_id: string;
    run_id: string | null;
    tool_call_id: string | null;
    principal_id: string;
    tool_name: string;
    risk: string;
    decision: string | null;
    success: boolean;
    duration: string | null;
    error: string | null;
    result_preview: string | null;
}

export interface RunDetail {
    run_id: string;
    parent_run_id: string | null;
    session_id: string;
    principal_id: string;
    role: string;
    status: string;
    created_at: string | null;
    updated_at: string | null;
    task: unknown;
    attempts: number;
    turn: number | null;
    result: unknown;
    error: string | null;
    errors: string[];
    usage: Record<string, unknown>;
    untrusted_context: boolean;
    pending_tool_call: ToolCall | null;
    queued_tool_calls: ToolCall[];
    last_feedback: string | null;
    observations: Observation[];
    audit: AuditEntry[];
}

// Statuses a run can still be cancelled from.
const CANCELLABLE = new Set(["queued", "running", "waiting_approval", "waiting_tool", "retrying"]);

function text(value: unknown): string {
    if (value === null || value === undefined) {
        return "-";
    }
    if (typeof value === "string") {
        return value;
    }
    if (typeof value === "object" && value !== null && "description" in value) {
        return String((value as { description: unknown }).description);
    }
    return JSON.stringify(value, null, 2);
}

export function TrustBadge({ trusted }: { trusted: boolean }) {
    return trusted ? (
        <span className={styles.badge} data-tone="ok">
            affidabile
        </span>
    ) : (
        <span className={styles.badge} data-tone="warn" title="Dati per il modello, mai istruzioni">
            non affidabile
        </span>
    );
}

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
    return (
        <section className={styles.section}>
            <h2 className={styles.h2}>
                {title.toUpperCase()} {count !== undefined && <span>{count}</span>}
            </h2>
            {children}
        </section>
    );
}

export default function RunDetailView({
    run,
    limits = null,
    timeline,
    onCancel,
}: {
    run: RunDetail;
    limits?: RunLimits | null;
    /** Shown after the task and the parked call (F2). */
    timeline?: React.ReactNode;
    onCancel?: () => void;
}) {
    const usage = toUsage(run.usage) ?? EMPTY_USAGE;
    const status = savedStatus(run.status);
    const tracked: TrackedRun = {
        id: run.run_id,
        parentId: run.parent_run_id,
        task: null,
        status: "finished",
        usage,
        usageAt: 0,
        startedAt: 0,
        endedAt: null,
        steps: [],
    };

    return (
        <div className={styles.stack}>
            <Section title="Panoramica">
                <div className={styles.card}>
                    <dl className={styles.facts}>
                        <dt>Stato</dt>
                        <dd data-testid="run-status" className={styles.row}>
                            <span className={styles.badge} data-tone={status.tone || undefined}>
                                {status.label}
                            </span>
                            {onCancel && CANCELLABLE.has(run.status) && (
                                <button type="button" onClick={onCancel} className={`${styles.btn} ${styles.danger}`}>
                                    Ferma la run
                                </button>
                            )}
                        </dd>
                        <dt>Creata</dt>
                        <dd className={styles.mono}>{localTime(run.created_at)}</dd>
                        <dt>Tentativi / turno</dt>
                        <dd className={styles.mono}>
                            {run.attempts} / {run.turn ?? "-"}
                        </dd>
                        {run.parent_run_id && (
                            <>
                                <dt>Run padre</dt>
                                <dd>
                                    <Link href={runHref(run.parent_run_id)} className={`${styles.link} ${styles.mono}`}>
                                        {run.parent_run_id}
                                    </Link>
                                </dd>
                            </>
                        )}
                        <dt>Consumo</dt>
                        <dd className={styles.mono}>
                            {usage.model_calls} chiamate al modello · {usage.tool_calls} tool · {usage.total_tokens} token
                        </dd>
                        <dt>Contesto</dt>
                        <dd>{run.untrusted_context ? "ha letto contenuti non affidabili" : "solo contenuti affidabili"}</dd>
                    </dl>
                    <RunMeters items={meters(tracked, limits, 0)} label="Limiti della run" />
                </div>
            </Section>

            <Section title="Compito">
                <pre className={styles.pre}>{text(run.task)}</pre>
            </Section>

            {run.pending_tool_call && (
                <Section title="Attende approvazione">
                    <div className={`${styles.card} ${styles.amber}`}>
                        <p className={styles.mono}>{run.pending_tool_call.tool_name}</p>
                        <pre className={styles.pre}>{JSON.stringify(run.pending_tool_call.arguments, null, 2)}</pre>
                        {run.queued_tool_calls.length > 0 && (
                            <p className={styles.muted}>Poi: {run.queued_tool_calls.map((call) => call.tool_name).join(", ")}</p>
                        )}
                        <Link href="/control-plane/approvals" className={styles.link}>
                            Decidi in Approvazioni →
                        </Link>
                    </div>
                </Section>
            )}

            {timeline}

            {(run.result !== null || run.error || run.errors.length > 0) && (
                <Section title="Esito">
                    {run.result !== null && <pre className={styles.pre}>{text(run.result)}</pre>}
                    {run.error && <p className={styles.error}>{run.error}</p>}
                    {run.errors.length > 0 && (
                        <ul className={styles.lines}>
                            {run.errors.map((item, index) => (
                                <li key={index} className={styles.error}>
                                    {item}
                                </li>
                            ))}
                        </ul>
                    )}
                    {run.last_feedback && <p className={styles.muted}>Critic: {run.last_feedback}</p>}
                </Section>
            )}

            <Section title="Risultati dei tool" count={run.observations.length}>
                {run.observations.length === 0 ? (
                    <p className={styles.muted}>Nessun tool ha ancora risposto.</p>
                ) : (
                    <ol className={`${styles.section} ${styles.plain}`}>
                        {run.observations.map((observation, index) => (
                            <li key={observation.tool_call_id ?? index} className={styles.card}>
                                <div className={styles.row}>
                                    <span className={styles.mono}>{observation.tool_name}</span>
                                    <TrustBadge trusted={observation.trusted} />
                                    {!observation.succeeded && (
                                        <span className={styles.badge} data-tone="bad">
                                            fallito
                                        </span>
                                    )}
                                    {observation.modified_file && (
                                        <span className={`${styles.muted} ${styles.mono}`}>ha scritto {observation.modified_file}</span>
                                    )}
                                </div>
                                <pre className={styles.pre}>{observation.content}</pre>
                            </li>
                        ))}
                    </ol>
                )}
            </Section>

            <Section title="Audit" count={run.audit.length}>
                {run.audit.length === 0 ? (
                    <p className={styles.muted}>Nessuna chiamata a tool registrata.</p>
                ) : (
                    <div className={styles.tableWrap}>
                        <table className={styles.table}>
                            <thead>
                                <tr>
                                    <th>Ora</th>
                                    <th>Tool</th>
                                    <th>Rischio</th>
                                    <th>Decisione</th>
                                    <th>Risultato</th>
                                </tr>
                            </thead>
                            <tbody>
                                {run.audit.map((entry) => (
                                    <tr key={entry.id}>
                                        <td className={styles.mono}>{entry.timestamp}</td>
                                        <td className={styles.mono}>{entry.tool_name}</td>
                                        <td className={styles.mono}>{entry.risk.toUpperCase()}</td>
                                        <td className={styles.mono}>{entry.decision ?? "-"}</td>
                                        <td>
                                            <span className={styles.badge} data-tone={entry.success ? "ok" : "bad"}>
                                                {entry.success ? "ok" : (entry.error ?? "fallito")}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Section>
        </div>
    );
}
