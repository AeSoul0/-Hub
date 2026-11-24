/**
 * @file frontend/src/lib/api/system.ts
 * @description The SISTEMA page (F9, ADR-030): what GET /api/system and its
 * sub-routes return, and the Italian names the page shows. Pure functions.
 */
import type { EngineEvent } from "@/lib/nucleo/engine";

export interface StartupParameter {
    name: string;
    value: string | null;
    source: "environment" | "default" | "unset";
}

export interface MemoryGroup {
    bytes: number;
    processes: number;
}

export type MemoryKind = "backend" | "postgres" | "browser" | "window" | "other";

export interface LoadedVoice {
    kind: "stt" | "tts";
    config: string[];
    idle_seconds: number;
}

export interface SystemView {
    app: {
        version: string | null;
        desktop: boolean;
        python: string;
        pid: number;
        started_at: string;
        uptime_seconds: number;
    };
    database: { ok: boolean; dialect: string; latency_ms: number | null; error: string | null };
    event_bus: { kind: "memory" | "redis"; ok: boolean; error: string | null };
    startup: StartupParameter[];
    memory: {
        groups: Record<MemoryKind, MemoryGroup>;
        total_bytes: number;
        machine: { total_bytes: number; available_bytes: number };
        voice: LoadedVoice[];
    };
    access_key: { can_rotate: boolean };
}

export interface UpdateCheck {
    current: string | null;
    latest: string | null;
    newer: boolean | null;
    published_at: string | null;
    notes: string | null;
    error: string | null;
}

export interface RecorderResult {
    matched: number;
    events: EngineEvent[];
    truncated: boolean;
    file_bytes: number;
}

export interface RecorderFilters {
    q: string;
    event_type: string;
    run_id: string;
}

export interface EvalCase {
    id: string;
    category: string;
    passed: boolean;
    critical: boolean;
    status: string;
    cost: number;
    failures: string[];
}

export interface EvalState {
    status: "idle" | "running" | "passed" | "failed" | "error";
    started_at: string | null;
    finished_at: string | null;
    started_by: string | null;
    gate: boolean;
    baseline: boolean;
    metrics: Record<string, number>;
    cases: EvalCase[];
    problems: string[];
    error: string | null;
}

export interface LogEntry {
    at: string;
    level: "warning" | "error" | "critical";
    logger: string;
    message: string;
}

export const PARAMETER_LABELS: Record<string, string> = {
    POSTGRES_URL: "Database",
    REDIS_URL: "Redis",
    AEHUB_EVENT_BUS: "Bus degli eventi",
    AEHUB_HOST: "Host dell'API",
    FRONTEND_URL: "Origine del frontend",
    AEHUB_ALLOWED_ORIGINS: "Altre origini permesse",
    AEHUB_DATA_DIR: "Cartella dei dati",
    AEHUB_ALLOWED_DIRS: "Cartella di lavoro dell'agente",
    AEHUB_VOICE_MODELS_DIR: "Modelli vocali",
    AEHUB_SKILL_INDEX_PATH: "Indice delle skill",
    AEHUB_FLIGHT_RECORDER_PATH: "Flight recorder",
    AEHUB_HOME_DEVICES: "File dei dispositivi",
    AEHUB_PG_BIN: "Programmi di PostgreSQL",
    AEHUB_FRONTEND_DIR: "Frontend servito dall'API",
};

export const SOURCE_LABELS: Record<StartupParameter["source"], string> = {
    environment: "dall'ambiente",
    default: "predefinito",
    unset: "non impostato",
};

export const MEMORY_LABELS: Record<MemoryKind, string> = {
    backend: "Backend (voce compresa)",
    postgres: "PostgreSQL",
    browser: "Chromium del browser",
    window: "Finestra dell'app",
    other: "Altri processi",
};

export const MEMORY_ORDER: MemoryKind[] = ["backend", "postgres", "browser", "window", "other"];

export const EVAL_STATUS: Record<EvalState["status"], { label: string; tone: "" | "ok" | "warn" | "bad" | "live" }> = {
    idle: { label: "mai avviati", tone: "" },
    running: { label: "in corso", tone: "live" },
    passed: { label: "superati", tone: "ok" },
    failed: { label: "non superati", tone: "bad" },
    error: { label: "errore", tone: "bad" },
};

export const METRIC_LABELS: Record<string, string> = {
    cases: "Casi",
    success_rate: "Successo",
    tool_accuracy: "Tool giusti",
    reliability: "Affidabilità",
    security_pass_rate: "Sicurezza",
    hallucination_rate: "Allucinazioni",
    mean_cost: "Costo medio",
    total_cost: "Costo totale",
    mean_latency_seconds: "Latenza media",
};

/** "1,2 GB", "340 MB", "12 KB": the page's sizes. */
export function bytesText(bytes: number): string {
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
        value /= 1024;
        unit += 1;
    }
    const digits = unit >= 3 && value < 10 ? 1 : 0;
    return `${value.toFixed(digits).replace(".", ",")} ${units[unit]}`;
}

/** "3 g 4 h", "2 h 5 min", "7 min", "40 s". */
export function uptimeText(seconds: number): string {
    const s = Math.max(0, Math.floor(seconds));
    const days = Math.floor(s / 86_400);
    const hours = Math.floor((s % 86_400) / 3600);
    const minutes = Math.floor((s % 3600) / 60);
    if (days > 0) {
        return `${days} g ${hours} h`;
    }
    if (hours > 0) {
        return `${hours} h ${minutes} min`;
    }
    return minutes > 0 ? `${minutes} min` : `${s} s`;
}

/** A rate metric as a percentage, a cost in dollars, a latency in seconds. */
export function metricText(name: string, value: number): string {
    if (name === "cases") {
        return String(value);
    }
    if (name.includes("cost")) {
        return `$${value.toFixed(4)}`;
    }
    if (name.includes("latency")) {
        return `${value.toFixed(2)} s`;
    }
    return `${Math.round(value * 1000) / 10}%`.replace(".", ",");
}

/** The voice model in memory, in words: "Whisper base, ferma da 3 min". */
export function voiceText(voice: LoadedVoice): string {
    const name = voice.kind === "stt" ? `Whisper ${voice.config[0] ?? ""}` : voice.config[0] === "elevenlabs" ? `Piper ${voice.config[3] ?? ""} (riserva di ElevenLabs)` : `Piper ${voice.config[1] ?? ""}`;
    return `${name.trim()}, ferma da ${uptimeText(voice.idle_seconds)}`;
}

/** "06/11 10:14:09" in local time, from a naive UTC timestamp of the backend. */
export function eventTime(timestamp: string | undefined): string {
    const parsed = timestamp ? Date.parse(timestamp.endsWith("Z") ? timestamp : `${timestamp}Z`) : NaN;
    if (Number.isNaN(parsed)) {
        return timestamp ?? "";
    }
    const date = new Date(parsed);
    const pad = (value: number) => String(value).padStart(2, "0");
    return `${pad(date.getDate())}/${pad(date.getMonth() + 1)} ${date.toTimeString().slice(0, 8)}`;
}

/** The query string of a recorder search or export: empty filters left out. */
export function recorderQuery(filters: RecorderFilters, extra: Record<string, string> = {}): string {
    const params = new URLSearchParams();
    for (const [name, value] of Object.entries({ ...filters, ...extra })) {
        if (value.trim()) {
            params.set(name, value.trim());
        }
    }
    const text = params.toString();
    return text ? `?${text}` : "";
}
