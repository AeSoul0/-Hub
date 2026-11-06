import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import SystemPage from "@/app/control-plane/system/page";
import { describe as describeEvent } from "@/lib/nucleo/engine";
import {
    bytesText,
    eventTime,
    metricText,
    recorderQuery,
    uptimeText,
    voiceText,
    type EvalState,
    type SystemView,
} from "@/lib/api/system";
import { VOICE_SETTINGS } from "@/lib/nucleo/voice";

import { stubFetch } from "./helpers";

function view(extra: Partial<SystemView> = {}): SystemView {
    return {
        app: { version: "1.0.0", desktop: true, python: "3.12.4", pid: 42, started_at: "2026-11-06T09:00:00", uptime_seconds: 3700 },
        database: { ok: true, dialect: "postgresql", latency_ms: 1.4, error: null },
        event_bus: { kind: "memory", ok: true, error: null },
        startup: [
            { name: "POSTGRES_URL", value: "postgresql://aehub:***@127.0.0.1:5432/aehub", source: "environment" },
            { name: "AEHUB_HOST", value: "127.0.0.1", source: "default" },
            { name: "AEHUB_PG_BIN", value: null, source: "unset" },
        ],
        memory: {
            groups: {
                backend: { bytes: 300 * 1024 * 1024, processes: 1 },
                postgres: { bytes: 40 * 1024 * 1024, processes: 6 },
                browser: { bytes: 0, processes: 0 },
                window: { bytes: 120 * 1024 * 1024, processes: 4 },
                other: { bytes: 0, processes: 0 },
            },
            total_bytes: 460 * 1024 * 1024,
            machine: { total_bytes: 8 * 1024 ** 3, available_bytes: 2.5 * 1024 ** 3 },
            voice: [{ kind: "stt", config: ["base", "it"], idle_seconds: 180 }],
        },
        access_key: { can_rotate: true },
        ...extra,
    };
}

function evals(extra: Partial<EvalState> = {}): EvalState {
    return {
        status: "idle",
        started_at: null,
        finished_at: null,
        started_by: null,
        gate: false,
        baseline: true,
        metrics: {},
        cases: [],
        problems: [],
        error: null,
        ...extra,
    };
}

function routes(extra: Record<string, () => { status: number; body: unknown }> = {}) {
    return stubFetch({
        "GET /api/system": () => ({ status: 200, body: view() }),
        "GET /api/system/evals": () => ({ status: 200, body: evals() }),
        "GET /api/system/logs": () => ({ status: 200, body: { logs: [] } }),
        ...extra,
    });
}

describe("system helpers", () => {
    it("say sizes, times and metrics the Italian way", () => {
        expect(bytesText(300 * 1024 * 1024)).toBe("300 MB");
        expect(bytesText(2.5 * 1024 ** 3)).toBe("2,5 GB");
        expect(bytesText(512)).toBe("512 B");
        expect(uptimeText(40)).toBe("40 s");
        expect(uptimeText(3700)).toBe("1 h 1 min");
        expect(uptimeText(3 * 86_400 + 4 * 3600)).toBe("3 g 4 h");
        expect(metricText("success_rate", 0.9545)).toBe("95,5%");
        expect(metricText("mean_cost", 0.0012)).toBe("$0.0012");
        expect(metricText("mean_latency_seconds", 0.25)).toBe("0.25 s");
        expect(metricText("cases", 44)).toBe("44");
    });

    it("name the voice models in memory", () => {
        expect(voiceText({ kind: "stt", config: ["base", "it"], idle_seconds: 180 })).toBe("Whisper base, ferma da 3 min");
        expect(voiceText({ kind: "tts", config: ["piper", "it_IT-paola-medium"], idle_seconds: 5 })).toBe(
            "Piper it_IT-paola-medium, ferma da 5 s",
        );
        expect(voiceText({ kind: "tts", config: ["elevenlabs", "v1", "m", "it_IT-paola-medium"], idle_seconds: 5 })).toBe(
            "Piper it_IT-paola-medium (riserva di ElevenLabs), ferma da 5 s",
        );
    });

    it("show an event's day and time in local time", () => {
        const local = new Date(Date.parse("2026-11-06T23:30:05Z"));
        const pad = (value: number) => String(value).padStart(2, "0");
        expect(eventTime("2026-11-06T23:30:05")).toBe(
            `${pad(local.getDate())}/${pad(local.getMonth() + 1)} ${local.toTimeString().slice(0, 8)}`,
        );
        expect(eventTime(undefined)).toBe("");
    });

    it("tell runs apart by what follows run_", () => {
        expect(describeEvent({ event_type: "run.started", run_id: "run_ab12cd34" }).detail).toBe("run ab12");
        expect(describeEvent({ event_type: "subagent.spawned", run_id: "run_9c1d", role: "research" }).detail).toBe("Research · 9c1d");
    });

    it("leave empty filters out of the recorder query", () => {
        expect(recorderQuery({ q: " luce ", event_type: "", run_id: "run-1" })).toBe("?q=luce&run_id=run-1");
        expect(recorderQuery({ q: "", event_type: "", run_id: "" })).toBe("");
    });

    it("put the voice switch on the VOCE page", () => {
        expect(VOICE_SETTINGS.slice(0, 2)).toEqual(["AEHUB_VOICE", "AEHUB_VOICE_IDLE_MINUTES"]);
    });
});

describe("the SISTEMA page", () => {
    it("shows the state, the memory and the startup parameters", async () => {
        routes();
        render(<SystemPage />);

        const database = await screen.findByRole("article", { name: "Database" });
        expect(within(database).getByText("raggiungibile")).toBeInTheDocument();
        expect(within(database).getByText("1.4 ms")).toBeInTheDocument();
        expect(within(screen.getByRole("article", { name: "Applicazione" })).getByText("app desktop")).toBeInTheDocument();
        expect(screen.getByText("In memoria, dentro il backend.")).toBeInTheDocument();

        const memory = screen.getByRole("table", { name: "Memoria dei processi" });
        expect(within(memory).getByText("PostgreSQL")).toBeInTheDocument();
        expect(within(memory).getByText("Finestra dell'app")).toBeInTheDocument();
        // A kind with no process is left out.
        expect(within(memory).queryByText("Chromium del browser")).not.toBeInTheDocument();
        expect(within(memory).getByText("460 MB")).toBeInTheDocument();
        expect(screen.getByText(/In memoria: Whisper base, ferma da 3 min/)).toBeInTheDocument();

        const startup = screen.getByRole("table", { name: "Parametri di avvio" });
        expect(within(startup).getByText("Database")).toBeInTheDocument();
        expect(within(startup).getByText("postgresql://aehub:***@127.0.0.1:5432/aehub")).toBeInTheDocument();
        expect(within(startup).getByText("predefinito")).toBeInTheDocument();
        expect(within(startup).getByText("non impostato")).toBeInTheDocument();
    });

    it("says when the database does not answer", async () => {
        routes({
            "GET /api/system": () => ({
                status: 200,
                body: view({ database: { ok: false, dialect: "postgresql", latency_ms: null, error: "OperationalError: refused" } }),
            }),
        });
        render(<SystemPage />);

        const database = await screen.findByRole("article", { name: "Database" });
        expect(within(database).getByText("non risponde")).toBeInTheDocument();
        expect(within(database).getByText("OperationalError: refused")).toBeInTheDocument();
    });

    it("checks for a desktop update", async () => {
        routes({
            "POST /api/system/updates/check": () => ({
                status: 200,
                body: { current: "1.0.0", latest: "1.1.0", newer: true, published_at: null, notes: "Correzioni.", error: null },
            }),
        });
        render(<SystemPage />);

        fireEvent.click(await screen.findByRole("button", { name: "Controlla adesso" }));

        expect(await screen.findByTestId("update-result")).toHaveTextContent(
            "È disponibile ÆHub 1.1.0 (questa è la 1.0.0): riavvia l'app per installarla.",
        );
        expect(screen.getByText("Correzioni.")).toBeInTheDocument();
    });

    it("searches and exports the flight recorder", async () => {
        const fetch = routes({
            "GET /api/system/events": () => ({
                status: 200,
                body: {
                    matched: 3,
                    truncated: true,
                    file_bytes: 2048,
                    events: [
                        { event_type: "checker.rejected", run_id: "run-1", timestamp: "2026-11-06T10:00:02", attempt: 1, details: { max_attempts: 3 } },
                        { event_type: "tool.completed", run_id: "run-1", timestamp: "2026-11-06T10:00:01", tool: "web_search" },
                    ],
                },
            }),
            "GET /api/system/events/export": () => ({ status: 200, body: "" }),
        });
        const created = vi.fn(() => "blob:export");
        // jsdom cannot follow a download link.
        vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
        vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }));
        render(<SystemPage />);

        const form = await screen.findByRole("form", { name: "Cerca nel flight recorder" });
        fireEvent.change(within(form).getByLabelText("Tipo"), { target: { value: "tool" } });
        fireEvent.click(within(form).getByRole("button", { name: "Cerca" }));

        const table = await screen.findByRole("table", { name: "Eventi trovati" });
        expect(within(table).getByText("tentativo 1 di 3 · respinto")).toBeInTheDocument();
        expect(within(table).getByText("web_search · ok")).toBeInTheDocument();
        expect(screen.getByText(/3 eventi trovati, qui i 2 più recenti · file di 2 KB/)).toBeInTheDocument();

        const search = fetch.mock.calls.map(([url]) => new URL(String(url))).find((url) => url.pathname === "/api/system/events");
        expect(search?.searchParams.get("event_type")).toBe("tool");

        fireEvent.click(within(form).getByRole("button", { name: "Esporta in JSONL" }));
        await waitFor(() => expect(created).toHaveBeenCalled());
        const exported = fetch.mock.calls.map(([url]) => new URL(String(url))).find((url) => url.pathname === "/api/system/events/export");
        expect(exported?.searchParams.get("event_type")).toBe("tool");
    });

    it("runs the evals and shows what failed", async () => {
        let state = evals();
        const fetch = routes({
            "GET /api/system/evals": () => ({ status: 200, body: state }),
            "POST /api/system/evals": () => {
                state = evals({
                    status: "failed",
                    gate: true,
                    finished_at: "2026-11-06T10:05:00",
                    metrics: { success_rate: 0.5, mean_cost: 0 },
                    cases: [
                        { id: "tools_ok", category: "tools", passed: true, critical: false, status: "COMPLETED", cost: 0, failures: [] },
                        { id: "leak_blocked", category: "security", passed: false, critical: true, status: "FAILED", cost: 0, failures: ["secret in the answer"] },
                    ],
                    problems: ["critical security cases failed: ['leak_blocked']"],
                });
                return { status: 202, body: state };
            },
        });
        render(<SystemPage />);

        expect(await screen.findByTestId("eval-status")).toHaveTextContent("mai avviati");
        fireEvent.click(screen.getByRole("button", { name: "Avvia gli eval" }));

        await waitFor(() => expect(screen.getByTestId("eval-status")).toHaveTextContent("non superati"));
        expect(fetch.mock.calls.some(([url, init]) => String(url).endsWith("/api/system/evals") && init?.method === "POST")).toBe(true);
        expect(screen.getByText("1 casi su 2 superati.", { exact: false })).toBeInTheDocument();
        const metrics = screen.getByLabelText("Metriche degli eval");
        expect(within(metrics).getByText("50%")).toBeInTheDocument();
        expect(within(screen.getByRole("list", { name: "Regressioni" })).getByText(/leak_blocked/)).toBeInTheDocument();
        const failed = screen.getByRole("list", { name: "Casi non superati" });
        expect(within(failed).getByText("critico")).toBeInTheDocument();
        expect(within(failed).getByText("secret in the answer")).toBeInTheDocument();
    });

    it("rotates the access key after a confirmation and shows it once", async () => {
        const fetch = routes({
            "POST /api/system/access-key/rotate": () => ({ status: 200, body: { key: "new-key-123", sessions_closed: 2 } }),
        });
        render(<SystemPage />);

        fireEvent.click(await screen.findByRole("button", { name: "Cambia la chiave" }));
        expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/access-key/rotate"))).toBe(false);
        fireEvent.click(screen.getByRole("button", { name: "Conferma: cambia la chiave" }));

        expect(await screen.findByTestId("new-key")).toHaveTextContent("new-key-123");
        expect(screen.getByText("Sessioni chiuse: 2.")).toBeInTheDocument();
        const call = fetch.mock.calls.find(([url]) => String(url).endsWith("/access-key/rotate"));
        expect(JSON.parse(String(call?.[1]?.body))).toEqual({ confirm: true });
    });

    it("says where the key lives when it cannot be rotated here", async () => {
        routes({ "GET /api/system": () => ({ status: 200, body: view({ access_key: { can_rotate: false } }) }) });
        render(<SystemPage />);

        expect(await screen.findByText(/si cambia dove è\s+impostata, poi si riavvia/)).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Cambia la chiave" })).not.toBeInTheDocument();
    });

    it("lists the recent warnings and errors", async () => {
        routes({
            "GET /api/system/logs": () => ({
                status: 200,
                body: {
                    logs: [
                        { at: "2026-11-06T10:00:00", level: "error", logger: "app.voice", message: "Piper failed" },
                        { at: "2026-11-06T09:00:00", level: "warning", logger: "app.home", message: "Broker slow" },
                    ],
                },
            }),
        });
        render(<SystemPage />);

        const list = await screen.findByRole("list", { name: "Avvisi ed errori" });
        expect(within(list).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
            expect.stringContaining("Piper failed"),
            expect.stringContaining("Broker slow"),
        ]);
    });
});
