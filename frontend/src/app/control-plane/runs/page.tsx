/**
 * @file frontend/src/app/control-plane/runs/page.tsx
 * @description Agent runs: kill switch, live runs against their limits, run
 * history with filters and the spend dashboard (roadmap M4, F2).
 *
 * Reads GET /api/runs/live, GET /api/runs (the history, filtered) and
 * GET /api/runs/stats, again whenever a run of the workspace changes state
 * (live events, no polling). A live run can be cancelled
 * (POST /api/runs/{id}/cancel); the global kill switch stops every run and
 * refuses new ones until resumed (POST /api/runs/stop-all, /resume).
 * Each run opens its own view (/control-plane/runs/view?id=...).
 */
"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useState } from "react";

import LiveBadge from "@/components/control-plane/LiveBadge";
import RunMeters from "@/components/control-plane/RunMeters";
import styles from "@/components/control-plane/control.module.css";
import { getJson, postJson } from "@/lib/api/client";
import { useLiveRefresh } from "@/lib/api/events";
import {
    duration,
    HISTORY_PAGE_SIZE,
    historyParams,
    localTime,
    meters,
    SAVED_STATUS_FILTERS,
    savedStatus,
    trackedFromLive,
    usd,
    type HistoryFilters,
    type LiveView,
    type RunUsage,
} from "@/lib/nucleo/runs";
import { runHref } from "@/lib/routes";

interface HistoryRun {
    run_id: string;
    parent_run_id: string | null;
    session_id: string;
    role: string;
    status: string;
    task: string | null;
    created_at: string | null;
    updated_at: string | null;
    error: string | null;
    usage: RunUsage;
}

interface History {
    total: number;
    limit: number;
    offset: number;
    runs: HistoryRun[];
}

interface RunStats {
    days: number;
    inferences_per_day: Record<string, Record<string, number>>;
    cost_by_role: Record<string, number>;
    cost_by_model: Record<string, number>;
    failed_tool_calls: { total: number; by_tool: Record<string, number> };
    cost_estimated: boolean;
    budget: {
        period: string;
        month_spent: number | null;
        monthly_budget: number;
        max_run_cost: number;
    };
}

const SEARCH_DEBOUNCE_MS = 300;
const DAYS = [1, 7, 30, 90, 366];

function Status({ status }: { status: string }) {
    const { label, tone } = savedStatus(status);
    return (
        <span className={styles.badge} data-tone={tone || undefined}>
            {label}
        </span>
    );
}

// Renders the run monitor, the history and the spend dashboard
export default function RunsPage() {
    const [live, setLive] = useState<LiveView | null>(null);
    const [stats, setStats] = useState<RunStats | null>(null);
    const [history, setHistory] = useState<History | null>(null);
    const [filters, setFilters] = useState<HistoryFilters>({ q: "", status: "", days: 30, subagents: true });
    const [search, setSearch] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [now, setNow] = useState(() => Date.now());

    const fail = (err: unknown) => setError(err instanceof Error ? err.message : String(err));

    const refreshLive = useCallback(async () => {
        try {
            const [liveView, runStats] = await Promise.all([
                getJson<LiveView>("/api/runs/live"),
                getJson<RunStats>("/api/runs/stats", { params: { days: 30 } }),
            ]);
            setLive(liveView);
            setStats(runStats);
            setNow(Date.now());
            setError(null);
        } catch (err) {
            fail(err);
        }
    }, []);

    const refreshHistory = useCallback(async () => {
        try {
            setHistory(await getJson<History>("/api/runs", { params: historyParams(filters) }));
        } catch (err) {
            fail(err);
        }
    }, [filters]);

    const refresh = useCallback(async () => {
        await Promise.all([refreshLive(), refreshHistory()]);
    }, [refreshLive, refreshHistory]);

    const liveState = useLiveRefresh(refresh, ["run.state", "run.resumed", "approval.decided"]);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    // Typing filters the history once the user pauses.
    useEffect(() => {
        const timer = setTimeout(() => setFilters((current) => (current.q === search ? current : { ...current, q: search })), SEARCH_DEBOUNCE_MS);
        return () => clearTimeout(timer);
    }, [search]);

    // The clocks of the live runs tick; their data comes from events.
    const ticking = Boolean(live?.runs.length);
    useEffect(() => {
        if (!ticking) {
            return;
        }
        const timer = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(timer);
    }, [ticking]);

    const act = async (endpoint: string) => {
        setBusy(true);
        try {
            await postJson(endpoint, {});
            await refresh();
        } catch (err) {
            fail(err);
        } finally {
            setBusy(false);
        }
    };

    const more = async () => {
        if (!history) {
            return;
        }
        try {
            const next = await getJson<History>("/api/runs", { params: historyParams(filters, history.runs.length) });
            setHistory({ ...next, runs: [...history.runs, ...next.runs] });
        } catch (err) {
            fail(err);
        }
    };

    const budget = stats?.budget;
    const spentRatio =
        budget && budget.month_spent !== null && budget.monthly_budget > 0 ? Math.min(1, budget.month_spent / budget.monthly_budget) : 0;

    return (
        <div className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>RUN</h1>
                <LiveBadge state={liveState} />
                <div className={styles.headEnd}>
                    {live?.halted ? (
                        <button type="button" onClick={() => act("/api/runs/resume")} disabled={busy} className={`${styles.btn} ${styles.ok}`}>
                            Riprendi gli agenti
                        </button>
                    ) : (
                        <button type="button" onClick={() => act("/api/runs/stop-all")} disabled={busy} className={`${styles.btn} ${styles.danger}`}>
                            FERMA TUTTO
                        </button>
                    )}
                </div>
            </div>

            {error && <p className={styles.error}>{error}</p>}
            {live?.halted && (
                <p className={styles.warn}>Motore fermato: le nuove run sono rifiutate finché non riprendi. {live.halt_reason}</p>
            )}

            <section className={styles.section} aria-labelledby="live-title">
                <h2 id="live-title" className={styles.h2}>
                    IN CORSO <span>{live?.runs.length || ""}</span>
                </h2>
                {!live || live.runs.length === 0 ? (
                    <p className={styles.muted}>Nessuna run in corso.</p>
                ) : (
                    <div className={styles.grid}>
                        {live.runs.map((run) => {
                            const tracked = trackedFromLive(run, now);
                            return (
                                <article key={run.run_id} className={styles.card} aria-label={`Run ${run.run_id}`}>
                                    <div className={styles.row}>
                                        <Link href={runHref(run.run_id)} className={`${styles.link} ${styles.mono}`}>
                                            {run.run_id.slice(0, 8)}
                                        </Link>
                                        {run.parent_run_id && <span className={styles.badge}>sub-agente</span>}
                                        <span className={styles.badge} data-tone={run.cancelling ? "bad" : "live"}>
                                            {run.cancelling ? "si sta fermando" : "in corso"}
                                        </span>
                                    </div>
                                    {run.task && <p className={styles.muted}>{run.task}</p>}
                                    <RunMeters items={meters(tracked, live.limits, now)} label={`Limiti della run ${run.run_id}`} />
                                    <div className={styles.row}>
                                        <button
                                            type="button"
                                            onClick={() => act(`/api/runs/${encodeURIComponent(run.run_id)}/cancel`)}
                                            disabled={busy || run.cancelling}
                                            className={`${styles.btn} ${styles.danger}`}
                                        >
                                            {run.cancelling ? "Si sta fermando…" : "Ferma la run"}
                                        </button>
                                    </div>
                                </article>
                            );
                        })}
                    </div>
                )}
            </section>

            {budget && (
                <section className={styles.section} aria-labelledby="budget-title">
                    <h2 id="budget-title" className={styles.h2}>
                        BUDGET <span>{budget.period}</span>
                    </h2>
                    <div className={styles.card}>
                        <ul className={styles.meters}>
                            <li data-level={spentRatio >= 1 ? "over" : spentRatio >= 0.8 ? "warn" : "ok"}>
                                <span>speso nel mese</span>
                                <span className={styles.bar} aria-hidden="true">
                                    <i style={{ width: `${spentRatio * 100}%` }} />
                                </span>
                                <span className={styles.meterText}>
                                    {budget.month_spent === null ? "-" : usd(budget.month_spent)} / {usd(budget.monthly_budget)}
                                </span>
                            </li>
                        </ul>
                        <p className={styles.muted}>
                            Limite per run {usd(budget.max_run_cost)}
                            {live?.limits && (
                                <>
                                    {" · "}tempo attivo {live.limits.max_run_seconds > 0 ? duration(live.limits.max_run_seconds) : "senza limite"}
                                    {" · "}tool falliti {live.limits.max_failed_tool_calls || "senza limite"}
                                    {" · "}file modificati {live.limits.max_files_modified || "senza limite"}
                                </>
                            )}
                        </p>
                        {stats?.cost_estimated && (
                            <p className={styles.warn}>Alcuni costi sono stimati: imposta i prezzi dei modelli in uso nelle Impostazioni.</p>
                        )}
                    </div>
                </section>
            )}

            <section className={styles.section} aria-labelledby="history-title">
                <h2 id="history-title" className={styles.h2}>
                    STORICO <span>{history ? history.total : ""}</span>
                </h2>
                <form className={styles.filters} role="search" onSubmit={(event) => event.preventDefault()}>
                    <label className={`${styles.field} ${styles.grow}`}>
                        Cerca
                        <input
                            type="search"
                            placeholder="testo del compito o id della run"
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                        />
                    </label>
                    <label className={styles.field}>
                        Stato
                        <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
                            {SAVED_STATUS_FILTERS.map((option) => (
                                <option key={option.value} value={option.value}>
                                    {option.label}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className={styles.field}>
                        Periodo
                        <select value={filters.days} onChange={(event) => setFilters({ ...filters, days: Number(event.target.value) })}>
                            {DAYS.map((days) => (
                                <option key={days} value={days}>
                                    {days === 1 ? "ultimo giorno" : days === 366 ? "ultimo anno" : `ultimi ${days} giorni`}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className={styles.check}>
                        <input
                            type="checkbox"
                            checked={filters.subagents}
                            onChange={(event) => setFilters({ ...filters, subagents: event.target.checked })}
                        />
                        anche i sub-agenti
                    </label>
                </form>

                {history && history.runs.length === 0 ? (
                    <p className={styles.muted}>Nessuna run con questi filtri.</p>
                ) : (
                    <div className={styles.tableWrap}>
                        <table className={styles.table}>
                            <thead>
                                <tr>
                                    <th>Run</th>
                                    <th>Compito</th>
                                    <th>Stato</th>
                                    <th>Inizio</th>
                                    <th className={styles.num}>Modello</th>
                                    <th className={styles.num}>Tool</th>
                                    <th className={styles.num}>Token</th>
                                    <th className={styles.num}>Costo</th>
                                    <th className={styles.num}>Tempo</th>
                                </tr>
                            </thead>
                            <tbody>
                                {history?.runs.map((run) => (
                                    <tr key={run.run_id}>
                                        <td className={styles.mono}>
                                            <Link href={runHref(run.run_id)} className={styles.link}>
                                                {run.run_id.slice(0, 8)}
                                            </Link>
                                            {run.parent_run_id && <span className={styles.sub}>sub-agente</span>}
                                        </td>
                                        <td className={styles.task}>
                                            {run.task ?? <span className={styles.faint}>-</span>}
                                            {run.error && <span className={styles.sub}>{run.error}</span>}
                                        </td>
                                        <td>
                                            <Status status={run.status} />
                                        </td>
                                        <td className={styles.mono}>{localTime(run.created_at)}</td>
                                        <td className={styles.num}>{run.usage.model_calls}</td>
                                        <td className={styles.num}>
                                            {run.usage.tool_calls}
                                            {run.usage.failed_tool_calls > 0 && <span className={styles.sub}>{run.usage.failed_tool_calls} falliti</span>}
                                        </td>
                                        <td className={styles.num}>{run.usage.total_tokens}</td>
                                        <td className={styles.num}>{usd(run.usage.cost)}</td>
                                        <td className={styles.num}>{duration(run.usage.active_seconds)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
                {history && history.runs.length < history.total && (
                    <div className={styles.row}>
                        <button type="button" className={styles.btn} onClick={() => void more()}>
                            Altre {Math.min(HISTORY_PAGE_SIZE, history.total - history.runs.length)}
                        </button>
                        <span className={styles.muted}>
                            {history.runs.length} di {history.total}
                        </span>
                    </div>
                )}
            </section>

            {stats && (
                <section className={styles.section} aria-labelledby="spend-title">
                    <h2 id="spend-title" className={styles.h2}>
                        SPESA <span>ultimi {stats.days} giorni</span>
                    </h2>
                    <div className={styles.grid}>
                        {(
                            [
                                ["Per ruolo", stats.cost_by_role],
                                ["Per modello", stats.cost_by_model],
                            ] as const
                        ).map(([title, costs]) => (
                            <div key={title} className={styles.card}>
                                <h3 className={styles.h2}>{title.toUpperCase()}</h3>
                                {Object.keys(costs).length === 0 ? (
                                    <p className={styles.muted}>Nessuna spesa.</p>
                                ) : (
                                    <ul className={styles.lines}>
                                        {Object.entries(costs).map(([name, cost]) => (
                                            <li key={name}>
                                                {name} <b>{usd(cost)}</b>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        ))}
                        <div className={styles.card}>
                            <h3 className={styles.h2}>
                                TOOL FALLITI <span>{stats.failed_tool_calls.total}</span>
                            </h3>
                            {stats.failed_tool_calls.total === 0 ? (
                                <p className={styles.muted}>Nessun tool fallito.</p>
                            ) : (
                                <ul className={styles.lines}>
                                    {Object.entries(stats.failed_tool_calls.by_tool).map(([tool, count]) => (
                                        <li key={tool}>
                                            {tool} <b>{count}</b>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>
                        <div className={styles.card}>
                            <h3 className={styles.h2}>INFERENZE PER GIORNO</h3>
                            {Object.keys(stats.inferences_per_day).length === 0 ? (
                                <p className={styles.muted}>Nessuna chiamata ai modelli.</p>
                            ) : (
                                <ul className={styles.lines}>
                                    {Object.entries(stats.inferences_per_day).map(([day, models]) => (
                                        <li key={day}>
                                            {day}{" "}
                                            <b>
                                                {Object.entries(models)
                                                    .map(([model, count]) => `${model} ×${count}`)
                                                    .join(", ")}
                                            </b>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>
                    </div>
                </section>
            )}
        </div>
    );
}
