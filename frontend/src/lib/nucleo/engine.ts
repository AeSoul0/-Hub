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
import { catalog, type Lang } from "@/lib/i18n";

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
    /** The attempt a Critic verdict is about (F8). */
    attempt?: number | null;
    details?: Record<string, unknown>;
}

export type LogKind = "run" | "model" | "tool" | "approval" | "voice" | "subagent" | "critic" | "deny" | "other";

// The worker roles by name (F8): a role chosen for a command or a subagent.
const ROLE_NAMES: Record<string, string> = {
    architect: "Architect",
    research: "Research",
    fast_worker: "Fast Worker",
    triage: "Triage",
};

export const roleName = (role: string | null | undefined) => (role ? (ROLE_NAMES[role] ?? role) : "");

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

// The engine's run ids all start with "run_": the part after it tells them apart.
const short = (id: string | null | undefined) => (id ? id.replace(/^run_/, "").slice(0, 4) : "");

// Backend timestamps are naive UTC.
export function clock(timestamp?: string): string {
    const parsed = timestamp ? Date.parse(timestamp.endsWith("Z") ? timestamp : `${timestamp}Z`) : NaN;
    const date = Number.isNaN(parsed) ? new Date() : new Date(parsed);
    return date.toTimeString().slice(0, 8);
}

function kindOf(name: string): LogKind {
    const head = name.split(".")[0];
    // The Critic's verdicts and the retries they ask for (F8).
    if (head === "checker" || head === "retry") {
        return "critic";
    }
    if (["run", "model", "tool", "approval", "voice", "subagent"].includes(head)) {
        return head as LogKind;
    }
    return "other";
}

const TEXT = catalog({
    en: {
        attempt: (attempt: number, max?: number) =>
            max === undefined ? `attempt ${attempt}` : `attempt ${attempt} of ${max}`,
        role: (role: string) => `role ${role}`,
        accepted: "accepted",
        skipped: "simple answer, not checked",
        rejected: "rejected",
        failed: "failed",
        retry: "new attempt",
        toolFailed: "failed",
        subagent: "subagent",
        budget: "monthly budget almost used up",
        plan: (done: number, total: number) => `plan: ${done} of ${total} steps done`,
    },
    it: {
        attempt: (attempt: number, max?: number) =>
            max === undefined ? `tentativo ${attempt}` : `tentativo ${attempt} di ${max}`,
        role: (role: string) => `ruolo ${role}`,
        accepted: "accettato",
        skipped: "risposta semplice, senza controllo",
        rejected: "respinto",
        failed: "bocciato",
        retry: "nuovo tentativo",
        toolFailed: "fallito",
        subagent: "sub-agente",
        budget: "budget del mese quasi esaurito",
        plan: (done: number, total: number) => `piano: ${done} di ${total} passi fatti`,
    },
});

/** "attempt 2 of 3" for a Critic verdict or a retry; "" without an attempt. */
export function attemptText(event: EngineEvent, lang: Lang = "en"): string {
    if (event.attempt == null) {
        return "";
    }
    const max = event.details?.max_attempts;
    return TEXT[lang].attempt(event.attempt, typeof max === "number" ? max : undefined);
}

/** The log line for one engine event. */
export function describe(event: EngineEvent, lang: Lang = "en"): Omit<LogLine, "id"> {
    const t = TEXT[lang];
    const name = event.event_type;
    const status = typeof event.details?.status === "string" ? event.details.status : "";
    const reason = typeof event.details?.reason === "string" ? event.details.reason : "";
    const instruction = typeof event.details?.retry_instruction === "string" ? event.details.retry_instruction : "";
    let detail: string;

    switch (name) {
        case "run.started":
            detail = [`run ${short(event.run_id)}`, event.role ? t.role(roleName(event.role)) : ""].filter(Boolean).join(" · ");
            break;
        case "checker.accepted":
            detail = [attemptText(event, lang), t.accepted].filter(Boolean).join(" · ");
            break;
        case "checker.skipped":
            detail = t.skipped;
            break;
        case "checker.rejected":
            detail = [attemptText(event, lang), t.rejected, instruction].filter(Boolean).join(" · ");
            break;
        case "checker.failed":
            detail = [attemptText(event, lang), t.failed, reason].filter(Boolean).join(" · ");
            break;
        case "retry.requested":
            detail = attemptText(event, lang) || t.retry;
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
        case "tool.completed":
            detail = [event.tool, event.details?.succeeded === false ? t.toolFailed : "ok"].filter(Boolean).join(" · ");
            break;
        case "subagent.spawned":
            detail = `${roleName(event.role) || t.subagent} · ${short(event.run_id)}`;
            break;
        case "subagent.completed":
            detail = [roleName(event.role) || t.subagent, status.toLowerCase()].filter(Boolean).join(" · ");
            break;
        case "budget.warning":
            detail = t.budget;
            break;
        case "plan.updated": {
            const steps = Array.isArray(event.details?.steps) ? (event.details.steps as { status?: string }[]) : [];
            detail = t.plan(steps.filter((step) => step.status === "done" || step.status === "skipped").length, steps.length);
            break;
        }
        default:
            detail = [`run ${short(event.run_id)}`, reason].filter(Boolean).join(" · ");
    }

    return {
        at: clock(event.timestamp),
        name,
        detail,
        risk: event.risk ? event.risk.toUpperCase() : undefined,
        kind:
            (name === "tool.completed" && event.details?.succeeded === false) || name === "checker.failed"
                ? "deny"
                : kindOf(name),
    };
}

export type NucleoAction =
    | { type: "engine"; event: EngineEvent; now: number; lang?: Lang }
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
            const next = withLine(state, describe(event, action.lang));

            switch (event.event_type) {
                case "run.started":
                    return { ...next, activeRuns: including(next.activeRuns, event.run_id) };
                case "run.completed":
                case "run.cancelled":
                case "run.limit_exceeded":
                case "budget.exceeded":
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
                        : { ...next, moons: [...next.moons, { id: event.run_id, label: event.role ?? "subagent" }] };
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

export const MODE_LABELS = catalog<Record<OrbMode, string>>({
    en: {
        idle: "WAITING",
        listening: "LISTENING",
        thinking: "THINKING",
        tool: "USING A TOOL",
        approval: "WAITING FOR YOUR APPROVAL",
        speaking: "SPEAKING",
    },
    it: {
        idle: "IN ATTESA",
        listening: "IN ASCOLTO",
        thinking: "STA RAGIONANDO",
        tool: "USA UN TOOL",
        approval: "ATTENDE LA TUA APPROVAZIONE",
        speaking: "STA PARLANDO",
    },
});

const MODE_TEXT = catalog({
    en: {
        idle: "Speak or type a command",
        listening: "microphone on · press again to send",
        subagents: (count: number) => `${count} subagents at work`,
        commands: (count: number) => `${count} commands at work`,
        working: "the engine is working",
        waiting: (count: number) => (count === 1 ? "1 action waiting" : `${count} actions waiting`),
        speaking: "local voice",
    },
    it: {
        idle: "Parla o scrivi un comando",
        listening: "microfono acceso · premi di nuovo per inviare",
        subagents: (count: number) => `${count} sub-agenti al lavoro`,
        commands: (count: number) => `${count} comandi al lavoro`,
        working: "il motore lavora",
        waiting: (count: number) => (count === 1 ? "1 azione in attesa" : `${count} azioni in attesa`),
        speaking: "voce locale",
    },
});

/**
 * The commands running together, as moons of the sphere (like subagents):
 * with one the sphere itself is the command; from two on, each has its moon,
 * named by the start of its text.
 */
export function commandMoons(commands: { id: string; task: string | null }[]): Moon[] {
    if (commands.length < 2) {
        return [];
    }
    return commands.map((command, index) => {
        const text = (command.task ?? "").trim();
        return {
            id: `command:${command.id}`,
            label: text ? (text.length > 14 ? `${text.slice(0, 13)}…` : text) : `#${index + 1}`,
        };
    });
}

export function modeDetail(mode: OrbMode, state: NucleoState, lang: Lang = "en", commands = 0): string {
    const t = MODE_TEXT[lang];
    if (mode === "thinking" && commands > 1) {
        return state.moons.length ? `${t.commands(commands)} · ${t.subagents(state.moons.length)}` : t.commands(commands);
    }
    switch (mode) {
        case "idle":
            return t.idle;
        case "listening":
            return t.listening;
        case "thinking":
            return state.moons.length ? t.subagents(state.moons.length) : state.modelName || t.working;
        case "tool":
            return state.toolName;
        case "approval":
            return t.waiting(state.waiting);
        case "speaking":
            return t.speaking;
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
