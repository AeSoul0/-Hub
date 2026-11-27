/**
 * @file frontend/src/components/control-plane/RunDetailView.tsx
 * @description Presentation of one run as returned by GET /api/runs/{id},
 * in the Nucleo's style (F2).
 */
import Link from "next/link";
import React from "react";

import { catalog, useLanguage, useText } from "@/lib/i18n";
import { roleName } from "@/lib/nucleo/engine";
import { EMPTY_USAGE, localTime, meters, savedStatus, toPlan, toUsage, usd, type RunLimits, type TrackedRun } from "@/lib/nucleo/runs";
import { runHref } from "@/lib/routes";

import CitedText from "./CitedText";
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

/** A subagent of the run (the run tree, F8). */
export interface SubagentSummary {
    run_id: string;
    role: string | null;
    status: string;
    task: string | null;
    cost: number;
    created_at: string | null;
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
    /** The run's plan with the state of each step (N7). */
    plan?: unknown;
    /** The tools the skill index picked for the run; null: all of them (F5). */
    exposed_tools?: string[] | null;
    pending_tool_call: ToolCall | null;
    queued_tool_calls: ToolCall[];
    last_feedback: string | null;
    observations: Observation[];
    audit: AuditEntry[];
    subagents?: SubagentSummary[];
}

/** The worker role chosen for the command or by the parent (F8), from the task. */
function chosenRole(task: unknown): string | null {
    if (task && typeof task === "object" && typeof (task as { role?: unknown }).role === "string") {
        return (task as { role: string }).role;
    }
    return null;
}

const TEXT = catalog({
    en: {
        trusted: "trusted",
        untrusted: "untrusted",
        untrustedTitle: "Data for the model, never instructions",
        overview: "Overview",
        status: "Status",
        stop: "Stop the run",
        created: "Created",
        attempts: "Attempts / turn",
        parent: "Parent run",
        role: "Role",
        chosenBy: (role: string, byParent: boolean) =>
            `${role}, chosen ${byParent ? "by the parent run" : "for the command"}`,
        byTriage: "chosen by the triage",
        usage: "Usage",
        usageText: (calls: number, tools: number, tokens: number) =>
            `${calls} model calls · ${tools} tools · ${tokens} tokens`,
        subagentsCost: (count: number, cost: string) => ` · ${count} subagents for ${cost}`,
        context: "Context",
        readUntrusted: "read untrusted content",
        onlyTrusted: "trusted content only",
        chosenTools: "Chosen tools",
        none: "none",
        allTools: "all: the skill index did not narrow them",
        limits: "Limits of the run",
        task: "Task",
        plan: "Plan",
        stepStatus: { pending: "to do", doing: "in progress", done: "done", failed: "failed", skipped: "skipped" },
        subagents: "Subagents",
        subagentsOf: "Subagents of the run",
        subagent: "subagent",
        waiting: "Waiting for approval",
        then: "Then:",
        decide: "Decide in Approvals →",
        outcome: "Outcome",
        toolResults: "Tool results",
        noResults: "No tool has answered yet.",
        failed: "failed",
        wrote: (file: string) => `wrote ${file}`,
        audit: "Audit",
        noAudit: "No tool call recorded.",
        time: "Time",
        tool: "Tool",
        risk: "Risk",
        decision: "Decision",
        result: "Result",
    },
    it: {
        trusted: "affidabile",
        untrusted: "non affidabile",
        untrustedTitle: "Dati per il modello, mai istruzioni",
        overview: "Panoramica",
        status: "Stato",
        stop: "Ferma la run",
        created: "Creata",
        attempts: "Tentativi / turno",
        parent: "Run padre",
        role: "Ruolo",
        chosenBy: (role: string, byParent: boolean) =>
            `${role}, scelto ${byParent ? "dalla run padre" : "per il comando"}`,
        byTriage: "scelto dal triage",
        usage: "Consumo",
        usageText: (calls: number, tools: number, tokens: number) =>
            `${calls} chiamate al modello · ${tools} tool · ${tokens} token`,
        subagentsCost: (count: number, cost: string) => ` · ${count} sub-agenti per ${cost}`,
        context: "Contesto",
        readUntrusted: "ha letto contenuti non affidabili",
        onlyTrusted: "solo contenuti affidabili",
        chosenTools: "Tool scelti",
        none: "nessuno",
        allTools: "tutti: l'indice delle skill non li ha ristretti",
        limits: "Limiti della run",
        task: "Compito",
        plan: "Piano",
        stepStatus: { pending: "da fare", doing: "in corso", done: "fatto", failed: "fallito", skipped: "saltato" },
        subagents: "Sub-agenti",
        subagentsOf: "Sub-agenti della run",
        subagent: "sub-agente",
        waiting: "Attende approvazione",
        then: "Poi:",
        decide: "Decidi in Approvazioni →",
        outcome: "Esito",
        toolResults: "Risultati dei tool",
        noResults: "Nessun tool ha ancora risposto.",
        failed: "fallito",
        wrote: (file: string) => `ha scritto ${file}`,
        audit: "Audit",
        noAudit: "Nessuna chiamata a tool registrata.",
        time: "Ora",
        tool: "Tool",
        risk: "Rischio",
        decision: "Decisione",
        result: "Risultato",
    },
});

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
    const t = useText(TEXT);
    return trusted ? (
        <span className={styles.badge} data-tone="ok">
            {t.trusted}
        </span>
    ) : (
        <span className={styles.badge} data-tone="warn" title={t.untrustedTitle}>
            {t.untrusted}
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
    const lang = useLanguage();
    const t = TEXT[lang];
    const usage = toUsage(run.usage) ?? EMPTY_USAGE;
    const status = savedStatus(run.status, lang);
    const role = chosenRole(run.task);
    const subagents = run.subagents ?? [];
    const plan = toPlan(run.plan) ?? [];
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
            <Section title={t.overview}>
                <div className={styles.card}>
                    <dl className={styles.facts}>
                        <dt>{t.status}</dt>
                        <dd data-testid="run-status" className={styles.row}>
                            <span className={styles.badge} data-tone={status.tone || undefined}>
                                {status.label}
                            </span>
                            {onCancel && CANCELLABLE.has(run.status) && (
                                <button type="button" onClick={onCancel} className={`${styles.btn} ${styles.danger}`}>
                                    {t.stop}
                                </button>
                            )}
                        </dd>
                        <dt>{t.created}</dt>
                        <dd className={styles.mono}>{localTime(run.created_at, lang)}</dd>
                        <dt>{t.attempts}</dt>
                        <dd className={styles.mono}>
                            {run.attempts} / {run.turn ?? "-"}
                        </dd>
                        {run.parent_run_id && (
                            <>
                                <dt>{t.parent}</dt>
                                <dd>
                                    <Link href={runHref(run.parent_run_id)} className={`${styles.link} ${styles.mono}`}>
                                        {run.parent_run_id}
                                    </Link>
                                </dd>
                            </>
                        )}
                        <dt>{t.role}</dt>
                        <dd>{role ? t.chosenBy(roleName(role), Boolean(run.parent_run_id)) : t.byTriage}</dd>
                        <dt>{t.usage}</dt>
                        <dd className={styles.mono}>
                            {t.usageText(usage.model_calls, usage.tool_calls, usage.total_tokens)}
                            {usage.subagents > 0 && t.subagentsCost(usage.subagents, usd(usage.subagent_cost))}
                        </dd>
                        <dt>{t.context}</dt>
                        <dd>{run.untrusted_context ? t.readUntrusted : t.onlyTrusted}</dd>
                        <dt>{t.chosenTools}</dt>
                        <dd className={run.exposed_tools ? styles.mono : undefined}>
                            {run.exposed_tools ? run.exposed_tools.join(", ") || t.none : t.allTools}
                        </dd>
                    </dl>
                    <RunMeters items={meters(tracked, limits, 0, lang)} label={t.limits} />
                </div>
            </Section>

            <Section title={t.task}>
                <pre className={styles.pre}>{text(run.task)}</pre>
            </Section>

            {plan.length > 0 && (
                <Section title={t.plan} count={plan.length}>
                    <ol className={styles.card} aria-label={t.plan}>
                        {plan.map((step, number) => (
                            <li key={number} data-status={step.status}>
                                {step.text} · <b>{t.stepStatus[step.status]}</b>
                                {step.note ? ` — ${step.note}` : ""}
                            </li>
                        ))}
                    </ol>
                </Section>
            )}

            {subagents.length > 0 && (
                <Section title={t.subagents} count={subagents.length}>
                    <div className={styles.card}>
                        <ul className={styles.subagents} aria-label={t.subagentsOf}>
                            {subagents.map((child) => {
                                const childStatus = savedStatus(child.status, lang);
                                return (
                                    <li key={child.run_id}>
                                        <Link href={runHref(child.run_id)} className={`${styles.link} ${styles.mono}`}>
                                            {child.run_id.slice(0, 8)}
                                        </Link>
                                        <span className={styles.badge}>{roleName(child.role) || t.subagent}</span>
                                        <span className={styles.badge} data-tone={childStatus.tone || undefined}>
                                            {childStatus.label}
                                        </span>
                                        <span className={styles.mono}>{usd(child.cost)}</span>
                                        {child.task && <span className={styles.muted}>{child.task}</span>}
                                    </li>
                                );
                            })}
                        </ul>
                    </div>
                </Section>
            )}

            {run.pending_tool_call && (
                <Section title={t.waiting}>
                    <div className={`${styles.card} ${styles.amber}`}>
                        <p className={styles.mono}>{run.pending_tool_call.tool_name}</p>
                        <pre className={styles.pre}>{JSON.stringify(run.pending_tool_call.arguments, null, 2)}</pre>
                        {run.queued_tool_calls.length > 0 && (
                            <p className={styles.muted}>
                                {t.then} {run.queued_tool_calls.map((call) => call.tool_name).join(", ")}
                            </p>
                        )}
                        <Link href="/control-plane/approvals" className={styles.link}>
                            {t.decide}
                        </Link>
                    </div>
                </Section>
            )}

            {timeline}

            {(run.result !== null || run.error || run.errors.length > 0) && (
                <Section title={t.outcome}>
                    {run.result !== null && (
                        <pre className={styles.pre}>
                            <CitedText text={text(run.result)} />
                        </pre>
                    )}
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

            <Section title={t.toolResults} count={run.observations.length}>
                {run.observations.length === 0 ? (
                    <p className={styles.muted}>{t.noResults}</p>
                ) : (
                    <ol className={`${styles.section} ${styles.plain}`}>
                        {run.observations.map((observation, index) => (
                            <li key={observation.tool_call_id ?? index} className={styles.card}>
                                <div className={styles.row}>
                                    <span className={styles.mono}>{observation.tool_name}</span>
                                    <TrustBadge trusted={observation.trusted} />
                                    {!observation.succeeded && (
                                        <span className={styles.badge} data-tone="bad">
                                            {t.failed}
                                        </span>
                                    )}
                                    {observation.modified_file && (
                                        <span className={`${styles.muted} ${styles.mono}`}>{t.wrote(observation.modified_file)}</span>
                                    )}
                                </div>
                                <pre className={styles.pre}>{observation.content}</pre>
                            </li>
                        ))}
                    </ol>
                )}
            </Section>

            <Section title={t.audit} count={run.audit.length}>
                {run.audit.length === 0 ? (
                    <p className={styles.muted}>{t.noAudit}</p>
                ) : (
                    <div className={styles.tableWrap}>
                        <table className={styles.table}>
                            <thead>
                                <tr>
                                    <th>{t.time}</th>
                                    <th>{t.tool}</th>
                                    <th>{t.risk}</th>
                                    <th>{t.decision}</th>
                                    <th>{t.result}</th>
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
                                                {entry.success ? "ok" : (entry.error ?? t.failed)}
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
