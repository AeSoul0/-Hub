/**
 * @file frontend/src/components/control-plane/RunDetailView.tsx
 * @description Presentation of one run as returned by GET /api/runs/{id}.
 */
import Link from "next/link";
import React from "react";

import { runHref } from "@/lib/routes";

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

function number(value: unknown, digits = 0): string {
    return typeof value === "number" ? value.toFixed(digits) : "-";
}

export function TrustBadge({ trusted }: { trusted: boolean }) {
    return trusted ? (
        <span className="text-xs px-2 py-0.5 rounded bg-green-900 text-green-200">trusted</span>
    ) : (
        <span className="text-xs px-2 py-0.5 rounded bg-yellow-900 text-yellow-200" title="Data for the model, never instructions">
            untrusted
        </span>
    );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <section className="mb-8">
            <h2 className="text-xl font-semibold mb-3">{title}</h2>
            {children}
        </section>
    );
}

export default function RunDetailView({ run, onCancel }: { run: RunDetail; onCancel?: () => void }) {
    const usage = run.usage;

    return (
        <div>
            <Section title="Overview">
                <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-sm">
                    <dt className="text-gray-400">Status</dt>
                    <dd data-testid="run-status" className="font-semibold">
                        {run.status}
                        {onCancel && CANCELLABLE.has(run.status) && (
                            <button
                                onClick={onCancel}
                                className="ml-4 bg-red-600 hover:bg-red-500 px-3 py-0.5 rounded text-xs"
                            >
                                Cancel
                            </button>
                        )}
                    </dd>
                    <dt className="text-gray-400">Created</dt>
                    <dd>{run.created_at ?? "-"}</dd>
                    <dt className="text-gray-400">Attempts / turn</dt>
                    <dd>
                        {run.attempts} / {run.turn ?? "-"}
                    </dd>
                    {run.parent_run_id && (
                        <>
                            <dt className="text-gray-400">Parent run</dt>
                            <dd>
                                <Link
                                    href={runHref(run.parent_run_id)}
                                    className="text-cyan-400 hover:underline font-mono"
                                >
                                    {run.parent_run_id}
                                </Link>
                            </dd>
                        </>
                    )}
                    <dt className="text-gray-400">Cost</dt>
                    <dd>
                        ${number(usage.cost, 4)} · {number(usage.model_calls)} model calls ·{" "}
                        {number(usage.tool_calls)} tool calls · {number(usage.total_tokens)} tokens ·{" "}
                        {number(usage.active_seconds, 1)} s active
                    </dd>
                    <dt className="text-gray-400">Context</dt>
                    <dd>{run.untrusted_context ? "has read untrusted content" : "trusted only"}</dd>
                </dl>
            </Section>

            <Section title="Task">
                <pre className="bg-black/40 rounded p-3 text-sm whitespace-pre-wrap">{text(run.task)}</pre>
            </Section>

            {run.pending_tool_call && (
                <Section title="Waiting for approval">
                    <p className="font-mono mb-2">{run.pending_tool_call.tool_name}</p>
                    <pre className="bg-black/40 rounded p-3 text-sm overflow-x-auto">
                        {JSON.stringify(run.pending_tool_call.arguments, null, 2)}
                    </pre>
                    {run.queued_tool_calls.length > 0 && (
                        <p className="text-gray-400 text-sm mt-2">
                            Then: {run.queued_tool_calls.map((call) => call.tool_name).join(", ")}
                        </p>
                    )}
                    <Link href="/control-plane/approvals" className="text-cyan-400 hover:underline text-sm">
                        Decide in Approvals →
                    </Link>
                </Section>
            )}

            {(run.result !== null || run.error || run.errors.length > 0) && (
                <Section title="Outcome">
                    {run.result !== null && (
                        <pre className="bg-black/40 rounded p-3 text-sm whitespace-pre-wrap mb-2">{text(run.result)}</pre>
                    )}
                    {run.error && <p className="text-red-400">{run.error}</p>}
                    {run.errors.length > 0 && (
                        <ul className="list-disc ml-6 text-sm text-red-300">
                            {run.errors.map((item, index) => (
                                <li key={index}>{item}</li>
                            ))}
                        </ul>
                    )}
                    {run.last_feedback && <p className="text-gray-400 text-sm mt-2">Checker: {run.last_feedback}</p>}
                </Section>
            )}

            <Section title={`Tool results (${run.observations.length})`}>
                {run.observations.length === 0 ? (
                    <p className="text-gray-400">No tool has returned yet.</p>
                ) : (
                    <ol className="space-y-3">
                        {run.observations.map((observation, index) => (
                            <li key={observation.tool_call_id ?? index} className="border border-gray-800 rounded p-3">
                                <div className="flex flex-wrap items-center gap-2 mb-2">
                                    <span className="font-mono">{observation.tool_name}</span>
                                    <TrustBadge trusted={observation.trusted} />
                                    {!observation.succeeded && <span className="text-xs text-red-400">failed</span>}
                                    {observation.modified_file && (
                                        <span className="text-xs text-gray-400 font-mono">
                                            wrote {observation.modified_file}
                                        </span>
                                    )}
                                </div>
                                <pre className="text-xs whitespace-pre-wrap text-gray-300">{observation.content}</pre>
                            </li>
                        ))}
                    </ol>
                )}
            </Section>

            <Section title={`Audit trail (${run.audit.length})`}>
                {run.audit.length === 0 ? (
                    <p className="text-gray-400">No audited tool call.</p>
                ) : (
                    <table className="w-full text-left border-collapse text-sm">
                        <thead>
                            <tr className="border-b border-gray-700">
                                <th className="p-2">Time</th>
                                <th className="p-2">Tool</th>
                                <th className="p-2">Risk</th>
                                <th className="p-2">Decision</th>
                                <th className="p-2">Result</th>
                            </tr>
                        </thead>
                        <tbody>
                            {run.audit.map((entry) => (
                                <tr key={entry.id} className="border-b border-gray-800">
                                    <td className="p-2 text-gray-400">{entry.timestamp}</td>
                                    <td className="p-2 font-mono">{entry.tool_name}</td>
                                    <td className="p-2 uppercase">{entry.risk}</td>
                                    <td className="p-2">{entry.decision ?? "-"}</td>
                                    <td className={`p-2 ${entry.success ? "text-green-400" : "text-red-400"}`}>
                                        {entry.success ? "ok" : (entry.error ?? "failed")}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </Section>
        </div>
    );
}
