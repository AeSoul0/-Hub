/**
 * @file frontend/tests/nucleo.test.tsx
 * @description Tests of the Nucleo: engine events, the sphere, resumed runs and side panes.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Nucleo from "@/components/nucleo/Nucleo";
import { clampHeight, MIN_HEIGHT } from "@/components/nucleo/SidePane";
import {
    commandMoons,
    describe as describeEvent,
    initialNucleo,
    LOG_LIMIT,
    modeDetail,
    nucleoReducer,
    orbMode,
    resumedReply,
    toEngineEvent,
    type EngineEvent,
    type NucleoState,
} from "@/lib/nucleo/engine";

import { installEventSource, stubFetch } from "./helpers";

import { chooseLanguage } from "@/lib/i18n";

// These tests read the Italian interface; interface.test.tsx covers the English default.
beforeEach(() => chooseLanguage("it"));

const quiet = { listening: false, speaking: false, sending: false };

const LIMITS = { max_run_cost: 2, max_run_seconds: 900, max_failed_tool_calls: 10, max_files_modified: 20, monthly_budget: 30 };

function liveRun(usage: Partial<Record<string, number>> = {}) {
    return {
        run_id: "run-1",
        session_id: "s",
        principal_id: "u",
        task: "Accendi la luce",
        started_at: "2026-10-24T10:00:00",
        cancelling: false,
        usage: { cost: 0, total_tokens: 0, model_calls: 0, tool_calls: 0, failed_tool_calls: 0, files_modified: 0, active_seconds: 0, ...usage },
    };
}

function liveView(extra: Record<string, unknown> = {}) {
    return { halted: false, halt_reason: null, limits: LIMITS, runs: [], ...extra };
}

function engine(event_type: string, extra: Partial<EngineEvent> = {}): EngineEvent {
    return { event_type, run_id: "run-1234", timestamp: "2026-10-24T10:00:00", ...extra };
}

function apply(...events: EngineEvent[]): NucleoState {
    return events.reduce((state, event) => nucleoReducer(state, { type: "engine", event, now: 1000 }), initialNucleo);
}

describe("engine events", () => {
    it("reads only engine events with a type and a run", () => {
        expect(toEngineEvent({ type: "engine.event", data: { event_type: "run.started", run_id: "r1" } })).toMatchObject({
            event_type: "run.started",
        });
        expect(toEngineEvent({ type: "run.state", data: { run_id: "r1" } })).toBeNull();
        expect(toEngineEvent({ type: "engine.event", data: { run_id: "r1" } })).toBeNull();
    });

    it("describes a model call and a call waiting for approval", () => {
        expect(describeEvent(engine("model.called", { model: "claude-sonnet-5-5", tokens: 1800, cost: 0.006, role: "worker" }))).toMatchObject({
            name: "model.called",
            detail: "claude-sonnet-5-5 · 1800 tok · $0.0060 · worker",
            kind: "model",
        });
        expect(describeEvent(engine("tool.approval_required", { tool: "home_unlock", risk: "high" }))).toMatchObject({
            detail: "home_unlock",
            risk: "HIGH",
            kind: "tool",
        });
        // The Critic's verdicts have their own kind (F8).
        expect(describeEvent(engine("checker.rejected")).kind).toBe("critic");
        expect(describeEvent(engine("budget.exceeded")).kind).toBe("other");
    });
});

describe("what the sphere does", () => {
    it("thinks while a run is active and stops when it completes", () => {
        const started = apply(engine("run.started"));
        expect(started.activeRuns).toEqual(["run-1234"]);
        expect(orbMode(started, quiet, 1000)).toBe("thinking");

        const done = nucleoReducer(started, { type: "engine", event: engine("run.completed"), now: 1000 });
        expect(done.activeRuns).toEqual([]);
        expect(orbMode(done, quiet, 1000)).toBe("idle");
    });

    it("scans for a moment on a tool call", () => {
        const state = apply(engine("run.started"), engine("tool.proposed", { tool: "home_set_light" }));
        expect(orbMode(state, quiet, 1500)).toBe("tool");
        expect(orbMode(state, quiet, 1000 + 5000)).toBe("thinking");
    });

    it("draws a moon per subagent until it completes", () => {
        const spawned = apply(engine("subagent.spawned", { run_id: "sub-1", role: "research" }));
        expect(spawned.moons).toEqual([{ id: "sub-1", label: "research" }]);
        expect(orbMode(spawned, quiet, 0)).toBe("thinking");

        const back = nucleoReducer(spawned, { type: "engine", event: engine("subagent.completed", { run_id: "sub-1" }), now: 0 });
        expect(back.moons).toEqual([]);
    });

    it("gives each command its moon when several run together", () => {
        // One command: the sphere itself is the command.
        expect(commandMoons([{ id: "a", task: "presentati" }])).toEqual([]);
        expect(
            commandMoons([
                { id: "a", task: "presentati" },
                { id: "b", task: "scrivi una storia lunga" },
                { id: "c", task: null },
            ])
        ).toEqual([
            { id: "command:a", label: "presentati" },
            { id: "command:b", label: "scrivi una st…" },
            { id: "command:c", label: "#3" },
        ]);
        const thinking = apply(engine("run.started"));
        expect(modeDetail("thinking", thinking, "it", 2)).toBe("2 comandi al lavoro");
        const withSub = apply(engine("subagent.spawned", { run_id: "sub-1", role: "research" }));
        expect(modeDetail("thinking", withSub, "it", 3)).toBe("3 comandi al lavoro · 1 sub-agenti al lavoro");
    });

    it("puts the user first: listening, speaking, then approvals", () => {
        const waiting = nucleoReducer(apply(engine("run.started")), { type: "approvals", count: 1 });
        expect(orbMode(waiting, quiet, 0)).toBe("approval");
        expect(orbMode(waiting, { ...quiet, speaking: true }, 0)).toBe("speaking");
        expect(orbMode(waiting, { ...quiet, listening: true, speaking: true }, 0)).toBe("listening");
    });

    it("leaves the thinking state when the run stops on its own", () => {
        const running = nucleoReducer(initialNucleo, { type: "runState", runId: "r9", state: "planning" });
        expect(running.activeRuns).toEqual(["r9"]);
        expect(nucleoReducer(running, { type: "runState", runId: "r9", state: "done" }).activeRuns).toEqual([]);
        expect(nucleoReducer(running, { type: "runState", runId: "r9", state: "awaiting_approval" }).activeRuns).toEqual([]);
    });

    it("keeps the log bounded", () => {
        let state = initialNucleo;
        for (let i = 0; i < LOG_LIMIT + 5; i++) {
            state = nucleoReducer(state, { type: "engine", event: engine("model.called"), now: 0 });
        }
        expect(state.log).toHaveLength(LOG_LIMIT);
        expect(state.log[0].id).toBe(6);
    });
});

describe("resumed runs", () => {
    it("finds the answer when the event carries one", () => {
        expect(resumedReply({ result: "Porta aperta." })).toBe("Porta aperta.");
        expect(resumedReply({ result: { result: "Fatto." } })).toBe("Fatto.");
        expect(resumedReply({ result: { messages: [{ content: "Prima" }, { content: "Ultima" }] } })).toBe("Ultima");
        expect(resumedReply({ result: { messages: [{ content: { status: "DONE" } }] } })).toBeNull();
        expect(resumedReply({ error: "Resume failed" })).toBeNull();
    });
});

describe("side panes", () => {
    it("stay between the minimum and just below the top bar", () => {
        expect(clampHeight(40, 600)).toBe(MIN_HEIGHT);
        expect(clampHeight(900, 600)).toBe(600);
        expect(clampHeight(321.4, 600)).toBe(321);
    });
});

describe("Nucleo", () => {
    beforeEach(() => {
        // jsdom has no canvas: the sphere simply does not draw.
        vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    });

    it("follows the engine and decides an approval", async () => {
        const Source = installEventSource();
        let pending: unknown[] = [];
        const fetch = stubFetch({
            "GET /api/approvals": () => ({ status: 200, body: pending }),
            "GET /api/runs/stats": () => ({
                status: 200,
                body: { budget: { month_spent: 0.21, monthly_budget: 2 } },
            }),
            "GET /api/runs/live": () => ({ status: 200, body: liveView() }),
            "POST /api/approvals/ap-1": () => ({ status: 200, body: { id: "ap-1", decision: "allow" } }),
        });

        render(<Nucleo />);
        const source = Source.instances[0];
        act(() => source.open());

        expect(await screen.findByText("$0.21")).toBeInTheDocument();
        expect(screen.getByText("IN ATTESA")).toBeInTheDocument();

        act(() => {
            source.emit("engine.event", { event_type: "run.started", run_id: "run-1", timestamp: "2026-10-24T10:00:00" });
            source.emit("engine.event", { event_type: "model.called", run_id: "run-1", model: "claude-sonnet-5-5", tokens: 900, cost: 0.002 });
        });
        expect(screen.getByText("run.started")).toBeInTheDocument();
        expect(screen.getByText("STA RAGIONANDO")).toBeInTheDocument();
        expect(screen.getByText("claude-sonnet-5-5")).toBeInTheDocument();

        pending = [
            {
                id: "ap-1",
                run_id: "run-1",
                session_id: "s",
                tool: "home_unlock",
                risk: "high",
                arguments_hash: "abc",
                arguments: { door: "ingresso" },
                requested_by: "u",
                requested_at: "2026-10-24T10:00:00",
                expires_at: "2999-01-01T00:00:00",
            },
        ];
        act(() => source.emit("approval.requested", { approval_id: "ap-1", run_id: "run-1", tool: "home_unlock" }));

        const allow = await screen.findByRole("button", { name: "Consenti" });
        expect(screen.getByText("ATTENDE LA TUA APPROVAZIONE")).toBeInTheDocument();
        expect(screen.getByText("door: ingresso")).toBeInTheDocument();

        pending = [];
        fireEvent.click(allow);
        await waitFor(() => expect(screen.queryByRole("button", { name: "Consenti" })).not.toBeInTheDocument());

        const decision = fetch.mock.calls.find(([, init]) => init?.method === "POST");
        expect(JSON.parse(String(decision?.[1]?.body))).toEqual({ decision: "allow" });
    });

    it("sends a typed command and shows the answer", async () => {
        installEventSource();
        const fetch = stubFetch({
            "GET /api/approvals": () => ({ status: 200, body: [] }),
            "GET /api/runs/stats": () => ({ status: 200, body: { budget: { month_spent: null, monthly_budget: 2 } } }),
            "GET /api/runs/live": () => ({ status: 200, body: liveView() }),
            "POST /api/orchestrator/ask": () => ({ status: 200, body: { transcription: "Luce accesa.", audio_base64: "" } }),
        });

        render(<Nucleo />);
        fireEvent.change(screen.getByRole("textbox", { name: "Comando" }), { target: { value: "Accendi la luce" } });
        fireEvent.click(screen.getByRole("button", { name: "INVIA" }));

        expect(await screen.findByText("Luce accesa.")).toBeInTheDocument();
        expect(screen.getByText("Accendi la luce")).toBeInTheDocument();

        const ask = fetch.mock.calls.find(([url]) => String(url).endsWith("/api/orchestrator/ask"));
        expect((ask?.[1]?.body as FormData).get("text")).toBe("Accendi la luce");
    });

    it("lists past conversations, goes on in one and starts a new one (N6)", async () => {
        installEventSource();
        const fetch = stubFetch({
            "GET /api/approvals": () => ({ status: 200, body: [] }),
            "GET /api/runs/stats": () => ({ status: 200, body: { budget: { month_spent: null, monthly_budget: 2 } } }),
            "GET /api/runs/live": () => ({ status: 200, body: liveView() }),
            "GET /api/conversations": () => ({
                status: 200,
                body: {
                    total: 2,
                    conversations: [
                        { id: "trip", title: "Organizza il viaggio", turns: 2, started_at: null, updated_at: null, match: null },
                        { id: "", title: "Che ore sono?", turns: 1, started_at: null, updated_at: null, match: null },
                    ],
                },
            }),
            "GET /api/conversations/trip": () => ({
                status: 200,
                body: {
                    id: "trip",
                    total: 2,
                    turns: [
                        { run_id: "r1", task: "Organizza il viaggio", answer: "Ecco il piano.", status: "completed", channel: "voice", created_at: null },
                        { run_id: "r2", task: "Aggiungi un museo", answer: "Comando fermato.", status: "cancelled", channel: "text", created_at: null },
                    ],
                },
            }),
            "GET /api/conversations/_": () => ({
                status: 200,
                body: { id: "", total: 1, turns: [{ run_id: "r0", task: "Che ore sono?", answer: "Le 9.", status: "completed", channel: "text", created_at: null }] },
            }),
            "POST /api/orchestrator/ask": () => ({ status: 200, body: { transcription: "Fatto.", audio_base64: "" } }),
        });

        render(<Nucleo />);
        fireEvent.click(screen.getByRole("button", { name: /CRONOLOGIA/ }));
        fireEvent.click(await screen.findByRole("button", { name: /Organizza il viaggio/ }));

        // Its turns are back in the conversation, and the next command goes on in it.
        expect(await screen.findByText("Ecco il piano.")).toBeInTheDocument();
        expect(screen.getByText("Comando fermato.")).toBeInTheDocument();
        fireEvent.change(screen.getByRole("textbox", { name: "Comando" }), { target: { value: "E il ritorno?" } });
        fireEvent.click(screen.getByRole("button", { name: "INVIA" }));
        expect(await screen.findByText("Fatto.")).toBeInTheDocument();
        const asks = () => fetch.mock.calls.filter(([url]) => String(url).endsWith("/api/orchestrator/ask"));
        expect((asks()[0][1]?.body as FormData).get("conversation")).toBe("trip");
        expect(window.localStorage.getItem("aehub.nucleo.conversation")).toBe("trip");

        // The principal's own session is the conversation "" (its path is /_).
        fireEvent.click(screen.getByRole("button", { name: /CRONOLOGIA/ }));
        fireEvent.click(await screen.findByRole("button", { name: /Che ore sono\?/ }));
        expect(await screen.findByText("Le 9.")).toBeInTheDocument();
        expect(window.localStorage.getItem("aehub.nucleo.conversation")).toBe("_");

        // A new one starts empty, with an id of its own.
        fireEvent.click(screen.getByRole("button", { name: /CRONOLOGIA/ }));
        fireEvent.click(await screen.findByRole("button", { name: "Nuova conversazione" }));
        expect(screen.queryByText("Le 9.")).not.toBeInTheDocument();
        fireEvent.change(screen.getByRole("textbox", { name: "Comando" }), { target: { value: "Ciao" } });
        fireEvent.click(screen.getByRole("button", { name: "INVIA" }));
        await waitFor(() => expect(asks()).toHaveLength(2));
        const fresh = (asks()[1][1]?.body as FormData).get("conversation");
        expect(fresh).toMatch(/^[A-Za-z0-9-]{1,64}$/);
        expect(fresh).not.toBe("trip");

        // The search goes to the backend, with what was typed.
        fireEvent.click(screen.getByRole("button", { name: /CRONOLOGIA/ }));
        fireEvent.change(screen.getByRole("searchbox", { name: "Cerca nelle conversazioni" }), { target: { value: "museo" } });
        await waitFor(() =>
            expect(fetch.mock.calls.some(([url]) => new URL(String(url)).searchParams.get("q") === "museo")).toBe(true),
        );
    });

    it("speaks the answer of a voice run resumed after an approval", async () => {
        const Source = installEventSource();
        const fetch = stubFetch({
            "GET /api/approvals": () => ({ status: 200, body: [] }),
            "GET /api/runs/stats": () => ({ status: 200, body: { budget: { month_spent: 0, monthly_budget: 2 } } }),
            "GET /api/runs/live": () => ({ status: 200, body: liveView() }),
            "POST /api/voice/speak": () => ({ status: 200, body: { audio_base64: "", audio_mime: "" } }),
        });

        render(<Nucleo />);
        act(() => Source.instances[0].open());

        act(() => Source.instances[0].emit("run.resumed", { run_id: "run-1", result: "Garage chiuso.", input_channel: "text" }));
        expect(await screen.findByText("Garage chiuso.")).toBeInTheDocument();

        act(() => Source.instances[0].emit("run.resumed", { run_id: "run-2", result: "Garage aperto.", input_channel: "voice" }));
        expect(await screen.findByText("Garage aperto.")).toBeInTheDocument();

        await waitFor(() => {
            const spoken = fetch.mock.calls.filter(([url]) => String(url).endsWith("/api/voice/speak"));
            expect(spoken).toHaveLength(1);
            // Sentence by sentence (N1), with the length of the whole reply.
            expect(JSON.parse(String(spoken[0][1]?.body))).toEqual({ text: "Garage aperto.", reply_chars: 14 });
        });
    });

    it("hides a pane and brings it back", () => {
        installEventSource();
        stubFetch({
            "GET /api/approvals": () => ({ status: 200, body: [] }),
            "GET /api/runs/stats": () => ({ status: 200, body: { budget: { month_spent: 0, monthly_budget: 2 } } }),
            "GET /api/runs/live": () => ({ status: 200, body: liveView() }),
        });

        render(<Nucleo />);
        const toggle = screen.getByRole("button", { name: "MOTORE" });
        const pane = document.getElementById("nucleo-events");

        expect(pane).toBeVisible();
        fireEvent.click(toggle);
        expect(toggle).toHaveAttribute("aria-pressed", "false");
        expect(pane).not.toBeVisible();
        fireEvent.click(toggle);
        expect(pane).toBeVisible();
    });

    it("follows a run against its limits and stops it, then everything", async () => {
        const Source = installEventSource();
        let halted = false;
        const fetch = stubFetch({
            "GET /api/approvals": () => ({ status: 200, body: [] }),
            "GET /api/runs/stats": () => ({ status: 200, body: { budget: { month_spent: 0, monthly_budget: 30 } } }),
            "GET /api/runs/live": () => ({
                status: 200,
                body: liveView({ halted, runs: halted ? [] : [liveRun({ cost: 0.5 })] }),
            }),
            "POST /api/runs/run-1/cancel": () => ({ status: 200, body: { run_id: "run-1", status: "cancelling" } }),
            "POST /api/runs/stop-all": () => {
                halted = true;
                return { status: 200, body: { halted: true, cancelled_runs: 1 } };
            },
        });

        render(<Nucleo />);
        act(() => Source.instances[0].open());

        fireEvent.click(screen.getByRole("button", { name: /^RUN/ }));
        expect(await screen.findByText("Accendi la luce")).toBeInTheDocument();
        const limits = screen.getByRole("list", { name: /^Limiti della run/ });
        expect(limits).toHaveTextContent("$0.5000 / $2.00");

        // The totals move with the live events, without asking again.
        act(() =>
            Source.instances[0].emit("engine.event", {
                event_type: "model.called",
                run_id: "run-1",
                cost: 1.3,
                details: { usage: { cost: 1.8, failed_tool_calls: 0, files_modified: 0, active_seconds: 4 } },
            }),
        );
        expect(limits).toHaveTextContent("$1.80 / $2.00");
        expect(screen.getByText("Σ $1.80")).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Ferma la run" }));
        await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/api/runs/run-1/cancel"))).toBe(true));

        const stopAll = screen.getByRole("button", { name: "FERMA TUTTO" });
        fireEvent.click(stopAll);
        expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/api/runs/stop-all"))).toBe(false);
        fireEvent.click(screen.getByRole("button", { name: "CONFERMI? FERMA TUTTO" }));

        expect(await screen.findByRole("button", { name: "MOTORE FERMO · RIPRENDI" })).toBeInTheDocument();
        expect(screen.getByText(/Motore fermato/)).toBeInTheDocument();
    });
});
