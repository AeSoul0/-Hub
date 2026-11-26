/**
 * @file frontend/src/lib/api/system.ts
 * @description The SISTEMA page (F9, ADR-030): what GET /api/system and its
 * sub-routes return, and the names the page shows in each interface
 * language. Pure functions.
 */

import { catalog, type Lang } from "@/lib/i18n";
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
    kind: "stt" | "tts" | "embedder";
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
    database: {
        ok: boolean;
        dialect: string;
        latency_ms: number | null;
        /** Alembic revision of the database (D1); null before the first migration. */
        revision: string | null;
        /** Newest revision shipped with this code. */
        head: string;
        error: string | null;
    };
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

export const PARAMETER_LABELS = catalog<Record<string, string>>({
    en: {
        POSTGRES_URL: "Database",
        REDIS_URL: "Redis",
        AEHUB_EVENT_BUS: "Event bus",
        AEHUB_HOST: "API host",
        AEHUB_ALLOWED_HOSTS: "Other API names",
        FRONTEND_URL: "Frontend origin",
        AEHUB_ALLOWED_ORIGINS: "Other allowed origins",
        AEHUB_DATA_DIR: "Data folder",
        AEHUB_ALLOWED_DIRS: "Agent's working folder",
        AEHUB_VOICE_MODELS_DIR: "Voice models",
        AEHUB_SKILL_INDEX_PATH: "Skill index",
        AEHUB_FLIGHT_RECORDER_PATH: "Flight recorder",
        AEHUB_HOME_DEVICES: "Devices file",
        AEHUB_PG_BIN: "PostgreSQL programs",
        AEHUB_FRONTEND_DIR: "Frontend served by the API",
        AEHUB_TELEMETRY_CONSOLE: "Traces in the console",
        ENVIRONMENT: "Environment (production: HTTPS-only cookies)",
        OPENAI_BASE_URL: "OpenAI address",
        OPENROUTER_BASE_URL: "OpenRouter address",
    },
    it: {
        POSTGRES_URL: "Database",
        REDIS_URL: "Redis",
        AEHUB_EVENT_BUS: "Bus degli eventi",
        AEHUB_HOST: "Host dell'API",
        AEHUB_ALLOWED_HOSTS: "Altri nomi dell'API",
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
        AEHUB_TELEMETRY_CONSOLE: "Tracce nella console",
        ENVIRONMENT: "Ambiente (production: cookie solo HTTPS)",
        OPENAI_BASE_URL: "Indirizzo di OpenAI",
        OPENROUTER_BASE_URL: "Indirizzo di OpenRouter",
    },
});

const API_PATHS = ["/docs", "/redoc", "/openapi.json", "/metrics", "/health"] as const;

type ApiPath = (typeof API_PATHS)[number];

const API_TEXT = catalog<Record<ApiPath, { label: string; help: string }>>({
    en: {
        "/docs": { label: "API documentation", help: "every route, to try out (Swagger)" },
        "/redoc": { label: "API reference", help: "the same documentation, to read" },
        "/openapi.json": { label: "OpenAPI schema", help: "to generate a client" },
        "/metrics": { label: "Prometheus metrics", help: "process and Python, for an external monitor" },
        "/health": { label: "Health check", help: "the containers' probe: always answers ok" },
    },
    it: {
        "/docs": { label: "Documentazione dell'API", help: "ogni route, da provare (Swagger)" },
        "/redoc": { label: "Riferimento dell'API", help: "la stessa documentazione, da leggere" },
        "/openapi.json": { label: "Schema OpenAPI", help: "per generare un client" },
        "/metrics": { label: "Metriche Prometheus", help: "processo e Python, per un monitor esterno" },
        "/health": { label: "Controllo di salute", help: "la sonda dei container: risponde sempre ok" },
    },
});

/** The API's own pages for tools and developers (F10): they need no login. */
export function apiPages(lang: Lang): { path: string; label: string; help: string }[] {
    return API_PATHS.map((path) => ({ path, ...API_TEXT[lang][path] }));
}

export const SOURCE_LABELS = catalog<Record<StartupParameter["source"], string>>({
    en: { environment: "from the environment", default: "default", unset: "not set" },
    it: { environment: "dall'ambiente", default: "predefinito", unset: "non impostato" },
});

export const MEMORY_LABELS = catalog<Record<MemoryKind, string>>({
    en: {
        backend: "Backend (voice included)",
        postgres: "PostgreSQL",
        browser: "Browser's Chromium",
        window: "App window",
        other: "Other processes",
    },
    it: {
        backend: "Backend (voce compresa)",
        postgres: "PostgreSQL",
        browser: "Chromium del browser",
        window: "Finestra dell'app",
        other: "Altri processi",
    },
});

export const MEMORY_ORDER: MemoryKind[] = ["backend", "postgres", "browser", "window", "other"];

type EvalTone = "" | "ok" | "warn" | "bad" | "live";

const EVAL_TONES: Record<EvalState["status"], EvalTone> = {
    idle: "",
    running: "live",
    passed: "ok",
    failed: "bad",
    error: "bad",
};

const EVAL_LABELS = catalog<Record<EvalState["status"], string>>({
    en: { idle: "never run", running: "running", passed: "passed", failed: "failed", error: "error" },
    it: { idle: "mai avviati", running: "in corso", passed: "superati", failed: "non superati", error: "errore" },
});

export function evalStatus(status: EvalState["status"], lang: Lang): { label: string; tone: EvalTone } {
    return { label: EVAL_LABELS[lang][status], tone: EVAL_TONES[status] };
}

export const METRIC_LABELS = catalog<Record<string, string>>({
    en: {
        cases: "Cases",
        success_rate: "Success",
        tool_accuracy: "Right tools",
        reliability: "Reliability",
        security_pass_rate: "Security",
        hallucination_rate: "Hallucinations",
        mean_cost: "Mean cost",
        total_cost: "Total cost",
        mean_latency_seconds: "Mean latency",
    },
    it: {
        cases: "Casi",
        success_rate: "Successo",
        tool_accuracy: "Tool giusti",
        reliability: "Affidabilità",
        security_pass_rate: "Sicurezza",
        hallucination_rate: "Allucinazioni",
        mean_cost: "Costo medio",
        total_cost: "Costo totale",
        mean_latency_seconds: "Latenza media",
    },
});

/** "1.2 GB", "340 MB", "12 KB" (Italian "1,2 GB"): the page's sizes. */
export function bytesText(bytes: number, lang: Lang = "en"): string {
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
        value /= 1024;
        unit += 1;
    }
    const digits = unit >= 3 && value < 10 ? 1 : 0;
    const text = value.toFixed(digits);
    return `${lang === "it" ? text.replace(".", ",") : text} ${units[unit]}`;
}

/** "3 d 4 h" (Italian "3 g 4 h"), "2 h 5 min", "7 min", "40 s". */
export function uptimeText(seconds: number, lang: Lang = "en"): string {
    const s = Math.max(0, Math.floor(seconds));
    const days = Math.floor(s / 86_400);
    const hours = Math.floor((s % 86_400) / 3600);
    const minutes = Math.floor((s % 3600) / 60);
    if (days > 0) {
        return `${days} ${lang === "it" ? "g" : "d"} ${hours} h`;
    }
    if (hours > 0) {
        return `${hours} h ${minutes} min`;
    }
    return minutes > 0 ? `${minutes} min` : `${s} s`;
}

/** A rate metric as a percentage, a cost in dollars, a latency in seconds. */
export function metricText(name: string, value: number, lang: Lang = "en"): string {
    if (name === "cases") {
        return String(value);
    }
    if (name.includes("cost")) {
        return `$${value.toFixed(4)}`;
    }
    if (name.includes("latency")) {
        return `${value.toFixed(2)} s`;
    }
    const percent = `${Math.round(value * 1000) / 10}%`;
    return lang === "it" ? percent.replace(".", ",") : percent;
}

const CLOUD_VOICES: Record<string, string> = { elevenlabs: "ElevenLabs", spacexai: "SpaceXAI" };

/** A local model in memory, in words: "Whisper base, idle for 3 min". */
export function voiceText(voice: LoadedVoice, lang: Lang = "en"): string {
    const cloud = CLOUD_VOICES[voice.config[0] ?? ""];
    const fallback = lang === "it" ? `riserva di ${cloud}` : `${cloud} fallback`;
    const memory = lang === "it" ? "memoria" : "memory";
    const name =
        voice.kind === "stt"
            ? `Whisper ${voice.config[0] ?? ""}`
            : voice.kind === "embedder"
              ? `${voice.config[0] ?? ""} (${memory})`
              : cloud
                ? `Piper ${voice.config[3] ?? ""} (${fallback})`
                : `Piper ${voice.config[1] ?? ""}`;
    const idle = uptimeText(voice.idle_seconds, lang);
    return lang === "it" ? `${name.trim()}, ferma da ${idle}` : `${name.trim()}, idle for ${idle}`;
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

/** The schema revision of the database against the newest one of the code (D1, ADR-031). */
export function schemaText(revision: string | null, head: string, lang: Lang = "en"): string {
    if (lang === "it") {
        if (!revision) return `non migrato (ultima ${head})`;
        return revision === head ? `${revision}, aggiornato` : `${revision}, da aggiornare a ${head}`;
    }
    if (!revision) return `not migrated (latest ${head})`;
    return revision === head ? `${revision}, up to date` : `${revision}, to upgrade to ${head}`;
}
