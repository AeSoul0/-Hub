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
    savedStatus,
    savedStatusFilters,
    trackedFromLive,
    treeRows,
    usd,
    type HistoryFilters,
    type LiveView,
    type RunUsage,
} from "@/lib/nucleo/runs";
import { catalog, useLanguage, useText } from "@/lib/i18n";
import { roleName } from "@/lib/nucleo/engine";
import { runHref } from "@/lib/routes";

interface HistoryRun {
    run_id: string;
    parent_run_id: string | null;
    session_id: string;
    role: string;
    /** The worker role chosen for the command or the subagent (F8). */
    chosen_role?: string | null;
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

const TEXT = catalog({
    en: {
        title: "RUNS",
        resume: "Resume the agents",
        stopAll: "STOP EVERYTHING",
        halted: "Engine stopped: new runs are refused until you resume.",
        live: "RUNNING",
        noLive: "No run in progress.",
        subagent: "subagent",
        stopping: "stopping",
        running: "running",
        limitsOf: (id: string) => `Limits of run ${id}`,
        stoppingButton: "Stopping…",
        stop: "Stop the run",
        spent: "spent this month",
        perRun: (cost: string) => `Limit per run ${cost}`,
        activeTime: "active time",
        failedTools: "failed tools",
        modifiedFiles: "modified files",
        noLimit: "no limit",
        estimated: "Some costs are estimated: set the prices of the models in use in Settings.",
        history: "HISTORY",
        search: "Search",
        searchPlaceholder: "text of the task or id of the run",
        status: "Status",
        period: "Period",
        days: (days: number) => (days === 1 ? "last day" : days === 366 ? "last year" : `last ${days} days`),
        withSubagents: "subagents too",
        noRuns: "No run with these filters.",
        task: "Task",
        start: "Start",
        model: "Model",
        tool: "Tool",
        tokens: "Tokens",
        cost: "Cost",
        time: "Time",
        role: (role: string) => `role ${role}`,
        failed: (count: number) => `${count} failed`,
        more: (count: number) => `${count} more`,
        of: (shown: number, total: number) => `${shown} of ${total}`,
        spend: "SPEND",
        lastDays: (days: number) => `last ${days} days`,
        byRole: "BY ROLE",
        byModel: "BY MODEL",
        noSpend: "No spend.",
        failedTitle: "FAILED TOOLS",
        noFailed: "No failed tool.",
        inferences: "INFERENCES PER DAY",
        noInferences: "No model calls.",
    },
    it: {
        title: "RUN",
        resume: "Riprendi gli agenti",
        stopAll: "FERMA TUTTO",
        halted: "Motore fermato: le nuove run sono rifiutate finché non riprendi.",
        live: "IN CORSO",
        noLive: "Nessuna run in corso.",
        subagent: "sub-agente",
        stopping: "si sta fermando",
        running: "in corso",
        limitsOf: (id: string) => `Limiti della run ${id}`,
        stoppingButton: "Si sta fermando…",
        stop: "Ferma la run",
        spent: "speso nel mese",
        perRun: (cost: string) => `Limite per run ${cost}`,
        activeTime: "tempo attivo",
        failedTools: "tool falliti",
        modifiedFiles: "file modificati",
        noLimit: "senza limite",
        estimated: "Alcuni costi sono stimati: imposta i prezzi dei modelli in uso nelle Impostazioni.",
        history: "STORICO",
        search: "Cerca",
        searchPlaceholder: "testo del compito o id della run",
        status: "Stato",
        period: "Periodo",
        days: (days: number) => (days === 1 ? "ultimo giorno" : days === 366 ? "ultimo anno" : `ultimi ${days} giorni`),
        withSubagents: "anche i sub-agenti",
        noRuns: "Nessuna run con questi filtri.",
        task: "Compito",
        start: "Inizio",
        model: "Modello",
        tool: "Tool",
        tokens: "Token",
        cost: "Costo",
        time: "Tempo",
        role: (role: string) => `ruolo ${role}`,
        failed: (count: number) => `${count} falliti`,
        more: (count: number) => `Altre ${count}`,
        of: (shown: number, total: number) => `${shown} di ${total}`,
        spend: "SPESA",
        lastDays: (days: number) => `ultimi ${days} giorni`,
        byRole: "PER RUOLO",
        byModel: "PER MODELLO",
        noSpend: "Nessuna spesa.",
        failedTitle: "TOOL FALLITI",
        noFailed: "Nessun tool fallito.",
        inferences: "INFERENZE PER GIORNO",
        noInferences: "Nessuna chiamata ai modelli.",
    },
});

const SEARCH_DEBOUNCE_MS = 300;
const DAYS = [1, 7, 30, 90, 366];

function Status({ status }: { status: string }) {
    const { label, tone } = savedStatus(status, useLanguage());
    return (
        <span className={styles.badge} data-tone={tone || undefined}>
            {label}
        </span>
    );
}

// Renders the run monitor, the history and the spend dashboard
export default function RunsPage() {
    const lang = useLanguage();
    const t = useText(TEXT);
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
                <h1 className={styles.title}>{t.title}</h1>
                <LiveBadge state={liveState} />
                <div className={styles.headEnd}>
                    {live?.halted ? (
                        <button type="button" onClick={() => act("/api/runs/resume")} disabled={busy} className={`${styles.btn} ${styles.ok}`}>
                            {t.resume}
                        </button>
                    ) : (
                        <button type="button" onClick={() => act("/api/runs/stop-all")} disabled={busy} className={`${styles.btn} ${styles.danger}`}>
                            {t.stopAll}
                        </button>
                    )}
                </div>
            </div>

            {error && <p className={styles.error}>{error}</p>}
            {live?.halted && (
                <p className={styles.warn}>
                    {t.halted} {live.halt_reason}
                </p>
            )}

            <section className={styles.section} aria-labelledby="live-title">
                <h2 id="live-title" className={styles.h2}>
                    {t.live} <span>{live?.runs.length || ""}</span>
                </h2>
                {!live || live.runs.length === 0 ? (
                    <p className={styles.muted}>{t.noLive}</p>
                ) : (
                    <div className={styles.grid}>
                        {treeRows(live.runs, (run) => run.started_at).map(({ run, depth }) => {
                            const tracked = trackedFromLive(run, now);
                            return (
                                <article
                                    key={run.run_id}
                                    className={styles.card}
                                    data-depth={depth || undefined}
                                    aria-label={`Run ${run.run_id}`}
                                >
                                    <div className={styles.row}>
                                        <Link href={runHref(run.run_id)} className={`${styles.link} ${styles.mono}`}>
                                            {run.run_id.slice(0, 8)}
                                        </Link>
                                        {run.parent_run_id && <span className={styles.badge}>{t.subagent}</span>}
                                        <span className={styles.badge} data-tone={run.cancelling ? "bad" : "live"}>
                                            {run.cancelling ? t.stopping : t.running}
                                        </span>
                                    </div>
                                    {run.task && <p className={styles.muted}>{run.task}</p>}
                                    <RunMeters items={meters(tracked, live.limits, now, lang)} label={t.limitsOf(run.run_id)} />
                                    <div className={styles.row}>
                                        <button
                                            type="button"
                                            onClick={() => act(`/api/runs/${encodeURIComponent(run.run_id)}/cancel`)}
                                            disabled={busy || run.cancelling}
                                            className={`${styles.btn} ${styles.danger}`}
                                        >
                                            {run.cancelling ? t.stoppingButton : t.stop}
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
                                <span>{t.spent}</span>
                                <span className={styles.bar} aria-hidden="true">
                                    <i style={{ width: `${spentRatio * 100}%` }} />
                                </span>
                                <span className={styles.meterText}>
                                    {budget.month_spent === null ? "-" : usd(budget.month_spent)} / {usd(budget.monthly_budget)}
                                </span>
                            </li>
                        </ul>
                        <p className={styles.muted}>
                            {t.perRun(usd(budget.max_run_cost))}
                            {live?.limits && (
                                <>
                                    {" · "}
                                    {t.activeTime}{" "}
                                    {live.limits.max_run_seconds > 0 ? duration(live.limits.max_run_seconds) : t.noLimit}
                                    {" · "}
                                    {t.failedTools} {live.limits.max_failed_tool_calls || t.noLimit}
                                    {" · "}
                                    {t.modifiedFiles} {live.limits.max_files_modified || t.noLimit}
                                </>
                            )}
                        </p>
                        {stats?.cost_estimated && (
                            <p className={styles.warn}>{t.estimated}</p>
                        )}
                    </div>
                </section>
            )}

            <section className={styles.section} aria-labelledby="history-title">
                <h2 id="history-title" className={styles.h2}>
                    {t.history} <span>{history ? history.total : ""}</span>
                </h2>
                <form className={styles.filters} role="search" onSubmit={(event) => event.preventDefault()}>
                    <label className={`${styles.field} ${styles.grow}`}>
                        {t.search}
                        <input
                            type="search"
                            placeholder={t.searchPlaceholder}
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                        />
                    </label>
                    <label className={styles.field}>
                        {t.status}
                        <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
                            {savedStatusFilters(lang).map((option) => (
                                <option key={option.value} value={option.value}>
                                    {option.label}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className={styles.field}>
                        {t.period}
                        <select value={filters.days} onChange={(event) => setFilters({ ...filters, days: Number(event.target.value) })}>
                            {DAYS.map((days) => (
                                <option key={days} value={days}>
                                    {t.days(days)}
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
                        {t.withSubagents}
                    </label>
                </form>

                {history && history.runs.length === 0 ? (
                    <p className={styles.muted}>{t.noRuns}</p>
                ) : (
                    <div className={styles.tableWrap}>
                        <table className={styles.table}>
                            <thead>
                                <tr>
                                    <th>Run</th>
                                    <th>{t.task}</th>
                                    <th>{t.status}</th>
                                    <th>{t.start}</th>
                                    <th className={styles.num}>{t.model}</th>
                                    <th className={styles.num}>{t.tool}</th>
                                    <th className={styles.num}>{t.tokens}</th>
                                    <th className={styles.num}>{t.cost}</th>
                                    <th className={styles.num}>{t.time}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {treeRows(history?.runs ?? [], (run) => run.created_at).map(({ run, depth }) => (
                                    <tr key={run.run_id} data-depth={depth || undefined}>
                                        <td className={styles.mono}>
                                            {depth > 0 && <span aria-hidden="true">↳ </span>}
                                            <Link href={runHref(run.run_id)} className={styles.link}>
                                                {run.run_id.slice(0, 8)}
                                            </Link>
                                            {run.parent_run_id && (
                                                <span className={styles.sub}>
                                                    {[t.subagent, roleName(run.chosen_role)].filter(Boolean).join(" · ")}
                                                </span>
                                            )}
                                            {!run.parent_run_id && run.chosen_role && (
                                                <span className={styles.sub}>{t.role(roleName(run.chosen_role))}</span>
                                            )}
                                        </td>
                                        <td className={styles.task}>
                                            {run.task ?? <span className={styles.faint}>-</span>}
                                            {run.error && <span className={styles.sub}>{run.error}</span>}
                                        </td>
                                        <td>
                                            <Status status={run.status} />
                                        </td>
                                        <td className={styles.mono}>{localTime(run.created_at, lang)}</td>
                                        <td className={styles.num}>{run.usage.model_calls}</td>
                                        <td className={styles.num}>
                                            {run.usage.tool_calls}
                                            {run.usage.failed_tool_calls > 0 && <span className={styles.sub}>{t.failed(run.usage.failed_tool_calls)}</span>}
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
                            {t.more(Math.min(HISTORY_PAGE_SIZE, history.total - history.runs.length))}
                        </button>
                        <span className={styles.muted}>
                            {t.of(history.runs.length, history.total)}
                        </span>
                    </div>
                )}
            </section>

            {stats && (
                <section className={styles.section} aria-labelledby="spend-title">
                    <h2 id="spend-title" className={styles.h2}>
                        {t.spend} <span>{t.lastDays(stats.days)}</span>
                    </h2>
                    <div className={styles.grid}>
                        {(
                            [
                                [t.byRole, stats.cost_by_role],
                                [t.byModel, stats.cost_by_model],
                            ] as const
                        ).map(([title, costs]) => (
                            <div key={title} className={styles.card}>
                                <h3 className={styles.h2}>{title}</h3>
                                {Object.keys(costs).length === 0 ? (
                                    <p className={styles.muted}>{t.noSpend}</p>
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
                                {t.failedTitle} <span>{stats.failed_tool_calls.total}</span>
                            </h3>
                            {stats.failed_tool_calls.total === 0 ? (
                                <p className={styles.muted}>{t.noFailed}</p>
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
                            <h3 className={styles.h2}>{t.inferences}</h3>
                            {Object.keys(stats.inferences_per_day).length === 0 ? (
                                <p className={styles.muted}>{t.noInferences}</p>
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
