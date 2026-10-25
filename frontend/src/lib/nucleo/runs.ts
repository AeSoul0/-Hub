/**
 * @file frontend/src/lib/nucleo/runs.ts
 * @description The runs the Nucleo follows (F2): their live totals next to
 * the per-run limits, and the timeline of each one.
 *
 * GET /api/runs/live gives the runs in progress, their totals and the
 * limits; `model.called` and `tool.completed` then carry the run totals
 * live, so the meters move without polling. Pure functions, like engine.ts.
 */
import { describe, type EngineEvent, type LogKind } from "./engine";

export interface RunUsage {
    cost: number;
    total_tokens: number;
    model_calls: number;
    tool_calls: number;
    failed_tool_calls: number;
    files_modified: number;
    active_seconds: number;
}

/** A limit of 0 is disabled. */
export interface RunLimits {
    max_run_cost: number;
    max_run_seconds: number;
    max_failed_tool_calls: number;
    max_files_modified: number;
    monthly_budget: number;
}

export interface LiveRunView {
    run_id: string;
    parent_run_id?: string | null;
    session_id: string;
    principal_id: string;
    role?: string | null;
    status?: string | null;
    task?: string | null;
    started_at: string;
    cancelling: boolean;
    usage: RunUsage;
}

export interface LiveView {
    halted: boolean;
    halt_reason: string | null;
    limits: RunLimits;
    runs: LiveRunView[];
}

export type RunStatus = "running" | "waiting" | "cancelling" | "completed" | "cancelled" | "failed" | "finished";

export interface Step {
    id: number;
    at: number;
    name: string;
    detail: string;
    kind: LogKind;
    /** The run's total cost after this step, when the event carries it. */
    total?: number;
}

export interface TrackedRun {
    id: string;
    parentId: string | null;
    task: string | null;
    status: RunStatus;
    usage: RunUsage;
    /** When `usage.active_seconds` was measured (ms). */
    usageAt: number;
    startedAt: number;
    endedAt: number | null;
    steps: Step[];
}

export interface RunsState {
    runs: TrackedRun[];
    limits: RunLimits | null;
    halted: boolean;
    haltReason: string | null;
    nextId: number;
}

// Finished runs stay on screen for their timeline, up to this many runs.
export const RUNS_KEPT = 8;
export const STEPS_KEPT = 120;

export const EMPTY_USAGE: RunUsage = {
    cost: 0,
    total_tokens: 0,
    model_calls: 0,
    tool_calls: 0,
    failed_tool_calls: 0,
    files_modified: 0,
    active_seconds: 0,
};

export const initialRuns: RunsState = { runs: [], limits: null, halted: false, haltReason: null, nextId: 1 };

const ENDED: ReadonlySet<RunStatus> = new Set(["completed", "cancelled", "failed", "finished"]);
// Statuses whose clock is running.
const TICKING: ReadonlySet<RunStatus> = new Set(["running", "cancelling"]);

export const isEnded = (run: TrackedRun) => ENDED.has(run.status);
export const canStop = (run: TrackedRun) => run.status === "running" || run.status === "waiting";

export const STATUS_LABELS: Record<RunStatus, string> = {
    running: "in corso",
    waiting: "attende approvazione",
    cancelling: "si sta fermando",
    completed: "completata",
    cancelled: "fermata",
    failed: "interrotta",
    finished: "finita",
};

/**
 * Run totals from a JSON object, a missing number as 0; the saved list of
 * modified files counts as its length.
 */
export function toUsage(value: unknown): RunUsage | null {
    if (!value || typeof value !== "object") {
        return null;
    }
    const record = value as Record<string, unknown>;
    const pick = (key: keyof RunUsage) => {
        const item = record[key];
        if (Array.isArray(item)) {
            return item.length;
        }
        return typeof item === "number" ? item : 0;
    };
    return {
        cost: pick("cost"),
        total_tokens: pick("total_tokens"),
        model_calls: pick("model_calls"),
        tool_calls: pick("tool_calls"),
        failed_tool_calls: pick("failed_tool_calls"),
        files_modified: pick("files_modified"),
        active_seconds: pick("active_seconds"),
    };
}

/** Run totals from an event's details, when it carries them. */
export const usageOf = (event: EngineEvent): RunUsage | null => toUsage(event.details?.usage);

// Backend timestamps are naive UTC.
function timeOf(timestamp: string | undefined, fallback: number): number {
    if (!timestamp) {
        return fallback;
    }
    const parsed = Date.parse(timestamp.endsWith("Z") ? timestamp : `${timestamp}Z`);
    return Number.isNaN(parsed) ? fallback : parsed;
}

function statusAfter(event: EngineEvent, current: RunStatus): RunStatus {
    switch (event.event_type) {
        case "run.completed":
            return "completed";
        case "run.cancelled":
            return "cancelled";
        case "run.limit_exceeded":
        case "budget.exceeded":
            return "failed";
        case "tool.approval_required":
            return "waiting";
        case "run.started":
        case "model.called":
        case "tool.proposed":
        case "tool.completed":
            // A resumed run works again; a stopping one keeps stopping.
            return current === "cancelling" || ENDED.has(current) ? current : "running";
        default:
            return current;
    }
}

function newRun(id: string, at: number, parentId: string | null = null): TrackedRun {
    return {
        id,
        parentId,
        task: null,
        status: "running",
        usage: EMPTY_USAGE,
        usageAt: at,
        startedAt: at,
        endedAt: null,
        steps: [],
    };
}

/** Keep the live runs and the most recent finished ones. */
function trim(runs: TrackedRun[]): TrackedRun[] {
    if (runs.length <= RUNS_KEPT) {
        return runs;
    }
    let extra = runs.length - RUNS_KEPT;
    return runs.filter((run) => {
        if (extra > 0 && isEnded(run)) {
            extra -= 1;
            return false;
        }
        return true;
    });
}

function upsert(runs: TrackedRun[], id: string, change: (run: TrackedRun) => TrackedRun, create: () => TrackedRun) {
    const index = runs.findIndex((run) => run.id === id);
    if (index === -1) {
        return trim([...runs, change(create())]);
    }
    const next = runs.slice();
    next[index] = change(runs[index]);
    return next;
}

function withStep(run: TrackedRun, step: Step): TrackedRun {
    const steps = [...run.steps, step];
    return { ...run, steps: steps.length > STEPS_KEPT ? steps.slice(steps.length - STEPS_KEPT) : steps };
}

export type RunsAction =
    | { type: "live"; view: LiveView; now: number }
    | { type: "event"; event: EngineEvent; now: number }
    | { type: "runState"; runId: string; state: string; now: number }
    | { type: "cancelling"; runId: string }
    | { type: "halt"; halted: boolean; reason?: string | null };

export function runsReducer(state: RunsState, action: RunsAction): RunsState {
    switch (action.type) {
        case "halt":
            return { ...state, halted: action.halted, haltReason: action.halted ? (action.reason ?? null) : null };

        case "cancelling":
            return {
                ...state,
                runs: state.runs.map((run) => (run.id === action.runId && canStop(run) ? { ...run, status: "cancelling" } : run)),
            };

        case "runState": {
            const { runId, now } = action;
            if (!state.runs.some((run) => run.id === runId)) {
                return state;
            }
            return {
                ...state,
                runs: state.runs.map((run) => {
                    if (run.id !== runId || isEnded(run)) {
                        return run;
                    }
                    if (action.state === "awaiting_approval") {
                        return { ...run, status: "waiting" };
                    }
                    if (action.state === "done") {
                        return { ...run, status: run.status === "cancelling" ? "cancelled" : "finished", endedAt: now };
                    }
                    return run.status === "waiting" ? { ...run, status: "running", usageAt: now } : run;
                }),
            };
        }

        case "live": {
            const { view, now } = action;
            const live = new Map(view.runs.map((run) => [run.run_id, run]));
            let runs = state.runs.map((run) => {
                const seen = live.get(run.id);
                if (seen) {
                    return {
                        ...run,
                        parentId: seen.parent_run_id ?? run.parentId,
                        task: seen.task ?? run.task,
                        usage: seen.usage,
                        usageAt: now,
                        status: seen.cancelling ? "cancelling" : "running",
                    } satisfies TrackedRun;
                }
                // A run parked on an approval is not live, and an ended one stays ended.
                if (run.status === "running" || run.status === "cancelling") {
                    return { ...run, status: run.status === "cancelling" ? "cancelled" : "finished", endedAt: now } satisfies TrackedRun;
                }
                return run;
            });
            for (const seen of view.runs) {
                if (!runs.some((run) => run.id === seen.run_id)) {
                    const startedAt = timeOf(seen.started_at, now);
                    runs.push({
                        ...newRun(seen.run_id, startedAt, seen.parent_run_id ?? null),
                        task: seen.task ?? null,
                        usage: seen.usage,
                        usageAt: now,
                        status: seen.cancelling ? "cancelling" : "running",
                    });
                }
            }
            runs = trim(runs);
            return { ...state, runs, limits: view.limits, halted: view.halted, haltReason: view.halt_reason };
        }

        case "event": {
            const { event, now } = action;
            const at = timeOf(event.timestamp, now);
            const line = describe(event);
            const usage = usageOf(event);
            let nextId = state.nextId;
            const step = (): Step => ({
                id: nextId++,
                at,
                name: line.name,
                detail: line.detail,
                kind: line.kind,
                total: usage?.cost ?? (event.event_type === "run.completed" && event.cost != null ? event.cost : undefined),
            });

            let runs = upsert(
                state.runs,
                event.run_id,
                (run) => {
                    const status = statusAfter(event, run.status);
                    const ended = ENDED.has(status) && !ENDED.has(run.status);
                    return withStep(
                        {
                            ...run,
                            parentId: event.parent_run_id ?? run.parentId,
                            status,
                            usage: usage ?? (event.event_type === "run.completed" && event.cost != null ? { ...run.usage, cost: event.cost } : run.usage),
                            usageAt: usage ? now : run.usageAt,
                            endedAt: ended ? at : run.endedAt,
                        },
                        step(),
                    );
                },
                () => newRun(event.run_id, at, event.parent_run_id ?? null),
            );

            // A subagent's start and end also mark its parent's timeline.
            const parentId = event.parent_run_id;
            if (parentId && event.event_type.startsWith("subagent.") && runs.some((run) => run.id === parentId)) {
                runs = runs.map((run) => (run.id === parentId ? withStep(run, step()) : run));
            }

            return { ...state, runs, nextId };
        }
    }
}

/** Seconds the run has been executing, ticking while it runs. */
export function elapsedSeconds(run: TrackedRun, now: number): number {
    const extra = TICKING.has(run.status) ? Math.max(0, now - run.usageAt) / 1000 : 0;
    return run.usage.active_seconds + extra;
}

export function duration(seconds: number): string {
    const total = Math.max(0, Math.floor(seconds));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const rest = String(total % 60).padStart(2, "0");
    return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

/** A backend timestamp (naive UTC) in local time: "25/10, 17:38". */
export function localTime(timestamp: string | null | undefined): string {
    if (!timestamp) {
        return "-";
    }
    const parsed = Date.parse(timestamp.endsWith("Z") ? timestamp : `${timestamp}Z`);
    return Number.isNaN(parsed)
        ? timestamp
        : new Date(parsed).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export const usd = (value: number) => `$${value.toFixed(value >= 1 ? 2 : 4)}`;

export interface Meter {
    key: "cost" | "time" | "failed" | "files";
    label: string;
    text: string;
    /** 0..1, 0 when the limit is disabled. */
    ratio: number;
    level: "ok" | "warn" | "over";
}

function meter(key: Meter["key"], label: string, value: number, max: number, show: (value: number) => string): Meter {
    const ratio = max > 0 ? Math.min(1, value / max) : 0;
    return {
        key,
        label,
        text: max > 0 ? `${show(value)} / ${show(max)}` : `${show(value)} · nessun limite`,
        ratio,
        level: max > 0 && value >= max ? "over" : ratio >= 0.8 ? "warn" : "ok",
    };
}

/** The run's totals against the per-run limits. */
export function meters(run: TrackedRun, limits: RunLimits | null, now: number): Meter[] {
    const usage = run.usage;
    return [
        meter("cost", "costo", usage.cost, limits?.max_run_cost ?? 0, usd),
        meter("time", "tempo attivo", elapsedSeconds(run, now), limits?.max_run_seconds ?? 0, duration),
        meter("failed", "tool falliti", usage.failed_tool_calls, limits?.max_failed_tool_calls ?? 0, String),
        meter("files", "file scritti", usage.files_modified, limits?.max_files_modified ?? 0, String),
    ];
}

/** A step's time from the start of the run: "+0.9 s" in the first minute, then "+1:07". */
export function offset(step: Step, run: TrackedRun): string {
    const seconds = Math.max(0, (step.at - run.startedAt) / 1000);
    return seconds < 60 ? `+${seconds.toFixed(1)} s` : `+${duration(seconds)}`;
}

/** The runs to show, live ones first, each group newest first; subagents follow their parent. */
export function ordered(runs: TrackedRun[]): TrackedRun[] {
    const ids = new Set(runs.map((run) => run.id));
    const roots = runs.filter((run) => !run.parentId || !ids.has(run.parentId));
    const byStart = (a: TrackedRun, b: TrackedRun) => b.startedAt - a.startedAt;
    const sorted = [...roots.filter((run) => !isEnded(run)).sort(byStart), ...roots.filter(isEnded).sort(byStart)];
    return sorted.flatMap((root) => [root, ...runs.filter((run) => run.parentId === root.id).sort(byStart)]);
}

export const liveCount = (state: RunsState) => state.runs.filter((run) => !isEnded(run)).length;

/** A live run of GET /api/runs/live, for the same meters as the Nucleo. */
export function trackedFromLive(view: LiveRunView, now: number): TrackedRun {
    return {
        ...newRun(view.run_id, timeOf(view.started_at, now), view.parent_run_id ?? null),
        task: view.task ?? null,
        usage: view.usage,
        usageAt: now,
        status: view.cancelling ? "cancelling" : "running",
    };
}

/** One recorded run rebuilt from its events (GET /api/runs/{id}/events). */
export function replay(runId: string, events: EngineEvent[]): TrackedRun | null {
    const state = events.reduce(
        (current, event) => runsReducer(current, { type: "event", event, now: timeOf(event.timestamp, 0) }),
        initialRuns,
    );
    return state.runs.find((run) => run.id === runId) ?? null;
}

export interface HistoryFilters {
    q: string;
    status: string;
    days: number;
    subagents: boolean;
}

export const HISTORY_PAGE_SIZE = 50;

/** The query string of GET /api/runs for these filters. */
export function historyParams(filters: HistoryFilters, offset = 0): Record<string, string | number | boolean> {
    const params: Record<string, string | number | boolean> = {
        days: filters.days,
        limit: HISTORY_PAGE_SIZE,
        offset,
        subagents: filters.subagents,
    };
    if (filters.q.trim()) {
        params.q = filters.q.trim();
    }
    if (filters.status) {
        params.status = filters.status;
    }
    return params;
}

export type Tone = "" | "ok" | "warn" | "bad" | "live";

// The statuses a run has in the database (app/agent_engine/models.py).
const SAVED_STATUSES: Record<string, { label: string; tone: Tone }> = {
    queued: { label: "in coda", tone: "" },
    running: { label: "in corso", tone: "live" },
    waiting_approval: { label: "attende approvazione", tone: "warn" },
    waiting_tool: { label: "attende un tool", tone: "live" },
    retrying: { label: "riprova", tone: "live" },
    completed: { label: "completata", tone: "ok" },
    failed: { label: "fallita", tone: "bad" },
    cancelled: { label: "fermata", tone: "bad" },
    expired: { label: "scaduta", tone: "bad" },
};

export function savedStatus(status: string): { label: string; tone: Tone } {
    return SAVED_STATUSES[status] ?? { label: status, tone: "" };
}

export const SAVED_STATUS_FILTERS: { value: string; label: string }[] = [
    { value: "", label: "tutti" },
    { value: "completed", label: "completate" },
    { value: "failed,expired", label: "fallite o scadute" },
    { value: "cancelled", label: "fermate" },
    { value: "waiting_approval", label: "in attesa di approvazione" },
    { value: "queued,running,waiting_tool,retrying", label: "in corso" },
];
