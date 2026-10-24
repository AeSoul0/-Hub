/**
 * @file frontend/src/app/control-plane/runs/page.tsx
 * @description Agent runs: kill switch and spend dashboard (roadmap M4).
 *
 * Reads GET /api/runs/live and GET /api/runs/stats, again whenever a run
 * of the workspace changes state (live events, no polling). A live run can be
 * cancelled (POST /api/runs/{id}/cancel); the global kill switch stops every
 * run and refuses new ones until resumed (POST /api/runs/stop-all, /resume).
 * Each run opens its own view (/control-plane/runs/view?id=...).
 */
"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useState } from "react";

import LiveBadge from "@/components/control-plane/LiveBadge";
import { getJson, postJson } from "@/lib/api/client";
import { useLiveRefresh } from "@/lib/api/events";
import { runHref } from "@/lib/routes";

interface LiveRun {
    run_id: string;
    session_id: string;
    principal_id: string;
    started_at: string;
    cancelling: boolean;
}

interface LiveState {
    halted: boolean;
    halt_reason: string | null;
    runs: LiveRun[];
}

interface RunSummary {
    run_id: string;
    session_id: string;
    status: string;
    created_at: string | null;
    model_calls: number;
    tool_calls: number;
    total_tokens: number;
    cost: number;
}

interface RunStats {
    days: number;
    inferences_per_day: Record<string, Record<string, number>>;
    cost_by_session: Record<string, number>;
    cost_by_role: Record<string, number>;
    cost_by_model: Record<string, number>;
    runs: RunSummary[];
    failed_tool_calls: { total: number; by_tool: Record<string, number> };
    cost_estimated: boolean;
    budget: {
        period: string;
        month_spent: number | null;
        monthly_budget: number;
        max_run_cost: number;
    };
}

function usd(value: number | null | undefined): string {
    return value === null || value === undefined ? "-" : `$${value.toFixed(4)}`;
}

function RunLink({ runId }: { runId: string }) {
    return (
        <Link href={runHref(runId)} className="text-cyan-400 hover:underline">
            {runId}
        </Link>
    );
}

// Renders the run monitor with the kill switch and the spend dashboard
export default function RunsPage() {
    const [live, setLive] = useState<LiveState | null>(null);
    const [stats, setStats] = useState<RunStats | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const refresh = useCallback(async () => {
        try {
            const [liveState, runStats] = await Promise.all([
                getJson<LiveState>("/api/runs/live"),
                getJson<RunStats>("/api/runs/stats?days=30"),
            ]);
            setLive(liveState);
            setStats(runStats);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        }
    }, []);

    const liveState = useLiveRefresh(refresh, ["run.state", "run.resumed", "approval.decided"]);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    const act = async (endpoint: string) => {
        setBusy(true);
        try {
            await postJson(endpoint, {});
            await refresh();
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setBusy(false);
        }
    };

    const budget = stats?.budget;
    const spentRatio =
        budget && budget.month_spent !== null && budget.monthly_budget > 0
            ? budget.month_spent / budget.monthly_budget
            : 0;

    return (
        <div className="p-8">
            <div className="flex items-center gap-4 mb-6">
                <h1 className="text-3xl font-bold text-orange-500">Agent Runs</h1>
                <LiveBadge state={liveState} />
            </div>

            {error && <p className="mb-4 text-red-400">{error}</p>}

            <section className="mb-8">
                <div className="flex items-center gap-4 mb-3">
                    <h2 className="text-xl font-semibold">Live runs</h2>
                    {live?.halted ? (
                        <button
                            onClick={() => act("/api/runs/resume")}
                            disabled={busy}
                            className="bg-green-600 hover:bg-green-500 disabled:opacity-50 px-4 py-1 rounded"
                        >
                            Resume agents
                        </button>
                    ) : (
                        <button
                            onClick={() => act("/api/runs/stop-all")}
                            disabled={busy}
                            className="bg-red-700 hover:bg-red-600 disabled:opacity-50 px-4 py-1 rounded font-bold"
                        >
                            STOP ALL
                        </button>
                    )}
                </div>

                {live?.halted && (
                    <p className="mb-3 text-red-400">
                        Kill switch active: new runs are refused. {live.halt_reason}
                    </p>
                )}

                {!live || live.runs.length === 0 ? (
                    <p className="text-gray-400">No run in progress.</p>
                ) : (
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="border-b border-gray-700">
                                <th className="p-2">Run</th>
                                <th className="p-2">Started</th>
                                <th className="p-2">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {live.runs.map((run) => (
                                <tr key={run.run_id} className="border-b border-gray-800">
                                    <td className="p-2 font-mono">
                                        <RunLink runId={run.run_id} />
                                    </td>
                                    <td className="p-2 text-gray-400">{run.started_at}</td>
                                    <td className="p-2">
                                        <button
                                            onClick={() =>
                                                act(`/api/runs/${encodeURIComponent(run.run_id)}/cancel`)
                                            }
                                            disabled={busy || run.cancelling}
                                            className="bg-red-600 hover:bg-red-500 disabled:opacity-50 px-4 py-1 rounded"
                                        >
                                            {run.cancelling ? "Cancelling..." : "Cancel"}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </section>

            {stats && budget && (
                <>
                    <section className="mb-8">
                        <h2 className="text-xl font-semibold mb-3">Budget ({budget.period})</h2>
                        <p className={spentRatio >= 0.8 ? "text-yellow-400" : "text-gray-300"}>
                            Spent this month: {usd(budget.month_spent)} of {usd(budget.monthly_budget)}
                            {" · "}per-run limit {usd(budget.max_run_cost)}
                        </p>
                        {stats.cost_estimated && (
                            <p className="text-yellow-500 text-sm mt-1">
                                Some costs are estimated: set AEHUB_MODEL_PRICES for the models in use.
                            </p>
                        )}
                    </section>

                    <section className="mb-8">
                        <h2 className="text-xl font-semibold mb-3">Inferences per day</h2>
                        {Object.keys(stats.inferences_per_day).length === 0 ? (
                            <p className="text-gray-400">No model calls in the last {stats.days} days.</p>
                        ) : (
                            <ul className="font-mono text-sm">
                                {Object.entries(stats.inferences_per_day).map(([day, models]) => (
                                    <li key={day}>
                                        {day}:{" "}
                                        {Object.entries(models)
                                            .map(([model, count]) => `${model} ×${count}`)
                                            .join(", ")}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>

                    <section className="mb-8 grid grid-cols-1 md:grid-cols-2 gap-6">
                        {(
                            [
                                ["Cost by role", stats.cost_by_role],
                                ["Cost by model", stats.cost_by_model],
                            ] as const
                        ).map(([title, costs]) => (
                            <div key={title}>
                                <h2 className="text-xl font-semibold mb-3">{title}</h2>
                                <ul className="font-mono text-sm">
                                    {Object.entries(costs).map(([name, cost]) => (
                                        <li key={name}>
                                            {name}: {usd(cost)}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        ))}
                    </section>

                    <section className="mb-8">
                        <h2 className="text-xl font-semibold mb-3">
                            Failed tool calls: {stats.failed_tool_calls.total}
                        </h2>
                        <ul className="font-mono text-sm">
                            {Object.entries(stats.failed_tool_calls.by_tool).map(([tool, count]) => (
                                <li key={tool}>
                                    {tool}: {count}
                                </li>
                            ))}
                        </ul>
                    </section>

                    <section>
                        <h2 className="text-xl font-semibold mb-3">Recent runs</h2>
                        <table className="w-full text-left border-collapse text-sm">
                            <thead>
                                <tr className="border-b border-gray-700">
                                    <th className="p-2">Run</th>
                                    <th className="p-2">Status</th>
                                    <th className="p-2">Model calls</th>
                                    <th className="p-2">Tool calls</th>
                                    <th className="p-2">Tokens</th>
                                    <th className="p-2">Cost</th>
                                </tr>
                            </thead>
                            <tbody>
                                {stats.runs.map((run) => (
                                    <tr key={run.run_id} className="border-b border-gray-800">
                                        <td className="p-2 font-mono">
                                            <RunLink runId={run.run_id} />
                                        </td>
                                        <td className="p-2">{run.status}</td>
                                        <td className="p-2">{run.model_calls}</td>
                                        <td className="p-2">{run.tool_calls}</td>
                                        <td className="p-2">{run.total_tokens}</td>
                                        <td className="p-2">{usd(run.cost)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </section>
                </>
            )}
        </div>
    );
}
