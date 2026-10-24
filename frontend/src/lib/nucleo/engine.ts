/**
 * @file frontend/src/lib/nucleo/engine.ts
 * @description What the Nucleo shows, derived from the engine's live events
 * (F1).
 *
 * The backend pushes every run event as `engine.event` on the workspace
 * stream, next to `run.state` and the approval events. This module turns
 * them into the sphere's mode, its moons (one per subagent) and the lines
 * of the event log. Pure functions, so the page stays a thin shell.
 */
import type { ControlEvent } from "@/lib/api/events";

export type OrbMode = "idle" | "listening" | "thinking" | "tool" | "approval" | "speaking";

/** One run event as the backend records it (app/agent_engine/events.py). */
export interface EngineEvent {
    event_type: string;
    run_id: string;
    parent_run_id?: string | null;
    timestamp?: string;
    tokens?: number | null;
    cost?: number | null;
    model?: string | null;
    role?: string | null;
    tool?: string | null;
    risk?: string | null;
    details?: Record<string, unknown>;
}

export type LogKind = "run" | "model" | "tool" | "approval" | "voice" | "subagent" | "deny" | "other";

export interface LogLine {
    id: number;
    at: string;
    name: string;
    detail: string;
    risk?: string;
    kind: LogKind;
}

export interface Moon {
    id: string;
    label: string;
}

export interface NucleoState {
    activeRuns: string[];
    waiting: number;
    moons: Moon[];
    toolUntil: number;
    toolName: string;
    modelName: string;
    log: LogLine[];
    nextId: number;
}

export const LOG_LIMIT = 200;
// How long a tool call keeps the scan on the sphere.
export const TOOL_FLASH_MS = 1400;

export const initialNucleo: NucleoState = {
    activeRuns: [],
    waiting: 0,
    moons: [],
    toolUntil: 0,
    toolName: "",
    modelName: "",
    log: [],
    nextId: 1,
};

export function toEngineEvent(event: ControlEvent): EngineEvent | null {
    if (event.type !== "engine.event") {
        return null;
    }
    const data = event.data;
    if (typeof data.event_type !== "string" || typeof data.run_id !== "string") {
        return null;
    }
    return data as unknown as EngineEvent;
}

const short = (id: string | null | undefined) => (id ? id.slice(0, 4) : "");

// Backend timestamps are naive UTC.
export function clock(timestamp?: string): string {
    const parsed = timestamp ? Date.parse(timestamp.endsWith("Z") ? timestamp : `${timestamp}Z`) : NaN;
    const date = Number.isNaN(parsed) ? new Date() : new Date(parsed);
    return date.toTimeString().slice(0, 8);
}

function kindOf(name: string): LogKind {
    const head = name.split(".")[0];
    if (["run", "model", "tool", "approval", "voice", "subagent"].includes(head)) {
        return head as LogKind;
    }
    return "other";
}

/** The log line for one engine event. */
export function describe(event: EngineEvent): Omit<LogLine, "id"> {
    const name = event.event_type;
    const status = typeof event.details?.status === "string" ? event.details.status : "";
    const reason = typeof event.details?.reason === "string" ? event.details.reason : "";
    let detail: string;

    switch (name) {
        case "run.started":
            detail = `run ${short(event.run_id)}`;
            break;
        case "model.called":
            detail = [
                event.model,
                event.tokens != null ? `${event.tokens} tok` : "",
                event.cost != null ? `$${event.cost.toFixed(4)}` : "",
                event.role,
            ]
                .filter(Boolean)
                .join(" · ");
            break;
        case "tool.proposed":
        case "tool.approval_required":
            detail = event.tool ?? "";
            break;
        case "subagent.spawned":
            detail = `${event.role ?? "sub-agente"} · ${short(event.run_id)}`;
            break;
        case "subagent.completed":
            detail = [event.role ?? "sub-agente", status.toLowerCase()].filter(Boolean).join(" · ");
            break;
        case "budget.warning":
            detail = "budget del mese quasi esaurito";
            break;
        default:
            detail = [`run ${short(event.run_id)}`, reason].filter(Boolean).join(" · ");
    }

    return {
        at: clock(event.timestamp),
        name,
        detail,
        risk: event.risk ? event.risk.toUpperCase() : undefined,
        kind: kindOf(name),
    };
}

export type NucleoAction =
    | { type: "engine"; event: EngineEvent; now: number }
    | { type: "runState"; runId: string; state: string }
    | { type: "approvals"; count: number }
    | { type: "note"; line: Omit<LogLine, "id"> };

function withLine(state: NucleoState, line: Omit<LogLine, "id">): NucleoState {
    const log = [...state.log, { ...line, id: state.nextId }];
    return {
        ...state,
        log: log.length > LOG_LIMIT ? log.slice(log.length - LOG_LIMIT) : log,
        nextId: state.nextId + 1,
    };
}

const without = (ids: string[], id: string) => ids.filter((item) => item !== id);
const including = (ids: string[], id: string) => (ids.includes(id) ? ids : [...ids, id]);

export function nucleoReducer(state: NucleoState, action: NucleoAction): NucleoState {
    switch (action.type) {
        case "note":
            return withLine(state, action.line);

        case "approvals":
            return { ...state, waiting: action.count };

        case "runState":
            if (action.state === "done") {
                return {
                    ...state,
                    activeRuns: without(state.activeRuns, action.runId),
                    moons: state.moons.filter((moon) => moon.id !== action.runId),
                };
            }
            if (action.state === "awaiting_approval") {
                return { ...state, activeRuns: without(state.activeRuns, action.runId) };
            }
            return { ...state, activeRuns: including(state.activeRuns, action.runId) };

        case "engine": {
            const { event, now } = action;
            const next = withLine(state, describe(event));

            switch (event.event_type) {
                case "run.started":
                    return { ...next, activeRuns: including(next.activeRuns, event.run_id) };
                case "run.completed":
                case "run.cancelled":
                    return {
                        ...next,
                        activeRuns: without(next.activeRuns, event.run_id),
                        moons: next.moons.filter((moon) => moon.id !== event.run_id),
                    };
                case "model.called":
                    return { ...next, modelName: event.model ?? next.modelName };
                case "tool.proposed":
                    return { ...next, toolUntil: now + TOOL_FLASH_MS, toolName: event.tool ?? "" };
                case "subagent.spawned":
                    return next.moons.some((moon) => moon.id === event.run_id)
                        ? next
                        : { ...next, moons: [...next.moons, { id: event.run_id, label: event.role ?? "sub-agente" }] };
                case "subagent.completed":
                    return { ...next, moons: next.moons.filter((moon) => moon.id !== event.run_id) };
                default:
                    return next;
            }
        }
    }
}

export interface LocalActivity {
    listening: boolean;
    speaking: boolean;
    sending: boolean;
}

/** The sphere's mode: what the user is doing first, then what the engine is doing. */
export function orbMode(state: NucleoState, local: LocalActivity, now: number): OrbMode {
    if (local.listening) return "listening";
    if (local.speaking) return "speaking";
    if (state.waiting > 0) return "approval";
    if (now < state.toolUntil) return "tool";
    if (local.sending || state.activeRuns.length > 0 || state.moons.length > 0) return "thinking";
    return "idle";
}

export const MODE_LABELS: Record<OrbMode, string> = {
    idle: "IN ATTESA",
    listening: "IN ASCOLTO",
    thinking: "STA RAGIONANDO",
    tool: "USA UN TOOL",
    approval: "ATTENDE LA TUA APPROVAZIONE",
    speaking: "STA PARLANDO",
};

export function modeDetail(mode: OrbMode, state: NucleoState): string {
    switch (mode) {
        case "idle":
            return "Parla o scrivi un comando";
        case "listening":
            return "microfono acceso · premi di nuovo per inviare";
        case "thinking":
            return state.moons.length
                ? `${state.moons.length} sub-agenti al lavoro`
                : state.modelName || "il motore lavora";
        case "tool":
            return state.toolName;
        case "approval":
            return state.waiting === 1 ? "1 azione in attesa" : `${state.waiting} azioni in attesa`;
        case "speaking":
            return "voce locale";
    }
}

/**
 * The answer of a run resumed after an approval, when `run.resumed` carries
 * one as text; null otherwise (the log still shows the event).
 */
export function resumedReply(data: Record<string, unknown>): string | null {
    const result = data.result;
    if (typeof result === "string") {
        return result || null;
    }
    if (!result || typeof result !== "object") {
        return null;
    }
    const record = result as Record<string, unknown>;
    if (typeof record.result === "string" && record.result) {
        return record.result;
    }
    const messages = record.messages;
    if (Array.isArray(messages) && messages.length) {
        const lastMessage = messages[messages.length - 1] as { content?: unknown } | string;
        const content = typeof lastMessage === "string" ? lastMessage : lastMessage?.content;
        if (typeof content === "string" && content) {
            return content;
        }
    }
    return null;
}
