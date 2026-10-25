import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import RunsPage from "@/app/control-plane/runs/page";
import RunTimeline from "@/components/control-plane/RunTimeline";
import RunsPanel from "@/components/nucleo/RunsPanel";
import type { EngineEvent } from "@/lib/nucleo/engine";
import {
    elapsedSeconds,
    EMPTY_USAGE,
    historyParams,
    initialRuns,
    meters,
    ordered,
    replay,
    RUNS_KEPT,
    runsReducer,
    savedStatus,
    toUsage,
    type LiveView,
    type RunsAction,
    type RunsState,
} from "@/lib/nucleo/runs";

import { installEventSource, stubFetch } from "./helpers";

const LIMITS = { max_run_cost: 2, max_run_seconds: 900, max_failed_tool_calls: 10, max_files_modified: 20, monthly_budget: 30 };
const START = Date.parse("2026-10-25T10:00:00Z");

function event(event_type: string, extra: Partial<EngineEvent> = {}, seconds = 0): EngineEvent {
    return {
        event_type,
        run_id: "run-1",
        timestamp: new Date(START + seconds * 1000).toISOString().replace("Z", ""),
        ...extra,
    };
}

function usage(values: Partial<typeof EMPTY_USAGE>) {
    return { details: { usage: { ...EMPTY_USAGE, ...values } } };
}

function apply(...actions: RunsAction[]): RunsState {
    return actions.reduce(runsReducer, initialRuns);
}

const on = (item: EngineEvent, now = START): RunsAction => ({ type: "event", event: item, now });

function view(extra: Partial<LiveView> = {}): LiveView {
    return { halted: false, halt_reason: null, limits: LIMITS, runs: [], ...extra };
}

describe("runs the Nucleo follows", () => {
    it("tracks totals, waiting and the end of a run from its events", () => {
        const state = apply(
            on(event("run.started")),
            on(event("model.called", { cost: 0.4, ...usage({ cost: 0.4, model_calls: 1, active_seconds: 2 }) }, 2)),
            on(event("tool.approval_required", { tool: "home_unlock" }, 3)),
        );
        const [run] = state.runs;
        expect(run.status).toBe("waiting");
        expect(run.usage.cost).toBe(0.4);
        expect(run.steps.map((step) => step.name)).toEqual(["run.started", "model.called", "tool.approval_required"]);
        expect(run.steps[1].total).toBe(0.4);

        const done = runsReducer(state, on(event("run.completed", { cost: 0.9 }, 9)));
        expect(done.runs[0].status).toBe("completed");
        expect(done.runs[0].usage.cost).toBe(0.9);
        expect(done.runs[0].endedAt).toBe(START + 9000);
    });

    it("marks a subagent's start and end on its parent too", () => {
        const state = apply(
            on(event("run.started")),
            on(event("subagent.spawned", { run_id: "sub-1", parent_run_id: "run-1", role: "research" }, 1)),
            on(event("subagent.completed", { run_id: "sub-1", parent_run_id: "run-1", role: "research" }, 5)),
        );
        const parent = state.runs.find((run) => run.id === "run-1");
        expect(parent?.steps.map((step) => step.name)).toEqual(["run.started", "subagent.spawned", "subagent.completed"]);
        expect(ordered(state.runs).map((run) => run.id)).toEqual(["run-1", "sub-1"]);
    });

    it("reads the live view and closes the runs that left it", () => {
        const live = apply({
            type: "live",
            now: START,
            view: view({
                runs: [
                    {
                        run_id: "run-1",
                        session_id: "s",
                        principal_id: "u",
                        task: "Accendi la luce",
                        started_at: "2026-10-25T09:59:50",
                        cancelling: false,
                        usage: { ...EMPTY_USAGE, active_seconds: 10 },
                    },
                ],
            }),
        });
        const [run] = live.runs;
        expect(run.task).toBe("Accendi la luce");
        expect(run.startedAt).toBe(START - 10000);
        // The clock ticks while the run runs.
        expect(elapsedSeconds(run, START + 5000)).toBe(15);

        const stopping = runsReducer(live, { type: "cancelling", runId: "run-1" });
        expect(stopping.runs[0].status).toBe("cancelling");

        const gone = runsReducer(stopping, { type: "live", now: START + 6000, view: view() });
        expect(gone.runs[0].status).toBe("cancelled");
        expect(elapsedSeconds(gone.runs[0], START + 60000)).toBe(10);
    });

    it("keeps a run parked on an approval when it leaves the live view", () => {
        const parked = apply(on(event("run.started")), { type: "runState", runId: "run-1", state: "awaiting_approval", now: START });
        expect(runsReducer(parked, { type: "live", now: START, view: view() }).runs[0].status).toBe("waiting");
    });

    it("keeps the live runs and only the most recent finished ones", () => {
        let state = initialRuns;
        for (let index = 0; index < RUNS_KEPT + 3; index++) {
            state = runsReducer(state, on(event("run.completed", { run_id: `done-${index}` }, index)));
        }
        state = runsReducer(state, on(event("run.started", { run_id: "live" }, 99)));
        expect(state.runs).toHaveLength(RUNS_KEPT);
        expect(state.runs.some((run) => run.id === "live")).toBe(true);
        expect(state.runs.some((run) => run.id === "done-0")).toBe(false);
    });

    it("measures each total against its limit", () => {
        const [run] = apply(on(event("model.called", usage({ cost: 1.7, failed_tool_calls: 10, files_modified: 3 })))).runs;
        const byKey = Object.fromEntries(meters(run, { ...LIMITS, max_files_modified: 0 }, START).map((item) => [item.key, item]));
        expect(byKey.cost).toMatchObject({ text: "$1.70 / $2.00", level: "warn" });
        expect(byKey.failed).toMatchObject({ text: "10 / 10", level: "over", ratio: 1 });
        expect(byKey.files).toMatchObject({ text: "3 · nessun limite", ratio: 0, level: "ok" });
        expect(byKey.time.text).toBe("0:00 / 15:00");
    });

    it("reads saved totals, counting the list of modified files", () => {
        expect(toUsage({ cost: 0.1, files_modified: ["a", "b"] })).toMatchObject({ cost: 0.1, files_modified: 2, tool_calls: 0 });
        expect(toUsage(null)).toBeNull();
    });
});

describe("recorded timeline", () => {
    const recorded = [
        event("run.started"),
        event("model.called", { model: "m", cost: 0.01, ...usage({ cost: 0.01 }) }, 3),
        event("tool.proposed", { tool: "ping" }, 4),
        event("tool.completed", { tool: "ping", details: { succeeded: false, usage: { ...EMPTY_USAGE, failed_tool_calls: 1 } } }, 5),
        event("run.completed", { cost: 0.01 }, 7),
    ];

    it("rebuilds the run from its events", () => {
        const run = replay("run-1", recorded);
        expect(run?.status).toBe("completed");
        expect(run?.steps.map((step) => step.name)).toEqual(["run.started", "model.called", "tool.proposed", "tool.completed", "run.completed"]);
        expect(replay("other", recorded)).toBeNull();
    });

    it("shows when each step happened and the cost so far", () => {
        render(<RunTimeline timeline={{ run_id: "run-1", truncated: false, events: recorded, limits: LIMITS }} />);
        const list = screen.getByRole("list", { name: "Timeline della run" });
        expect(list).toHaveTextContent("+3.0 s");
        expect(list).toHaveTextContent("ping · fallito");
        expect(screen.getAllByText("Σ $0.0100")).toHaveLength(2);
    });
});

describe("RunsPanel", () => {
    it("stops only a live run and opens the newest timeline", () => {
        const state = apply(
            on(event("run.completed", { run_id: "old" }, 0)),
            on(event("run.started", { run_id: "run-1" }, 10)),
            on(event("tool.proposed", { run_id: "run-1", tool: "ping" }, 12)),
        );
        const onStop = vi.fn();
        render(<RunsPanel state={{ ...state, limits: LIMITS }} onStop={onStop} />);

        const stops = screen.getAllByRole("button", { name: "Ferma la run" });
        expect(stops).toHaveLength(1);
        fireEvent.click(stops[0]);
        expect(onStop).toHaveBeenCalledWith("run-1");

        const [newest, older] = screen.getAllByRole("button", { name: /^Timeline/ });
        expect(newest).toHaveAttribute("aria-expanded", "true");
        expect(older).toHaveAttribute("aria-expanded", "false");
        expect(screen.getByText("+2.0 s")).toBeInTheDocument();

        fireEvent.click(older);
        expect(older).toHaveAttribute("aria-expanded", "true");
    });

    it("says where runs come from when there is none", () => {
        render(<RunsPanel state={initialRuns} onStop={vi.fn()} />);
        expect(screen.getByRole("link", { name: "Storico delle run" })).toHaveAttribute("href", "/control-plane/runs");
    });
});

describe("run history", () => {
    it("turns the filters into the query", () => {
        expect(historyParams({ q: "  luce ", status: "failed,expired", days: 7, subagents: false }, 50)).toEqual({
            q: "luce",
            status: "failed,expired",
            days: 7,
            subagents: false,
            limit: 50,
            offset: 50,
        });
        expect(historyParams({ q: " ", status: "", days: 30, subagents: true })).not.toHaveProperty("q");
        expect(savedStatus("completed")).toEqual({ label: "completata", tone: "ok" });
        expect(savedStatus("strange").label).toBe("strange");
    });

    it("filters the history from the page", async () => {
        installEventSource();
        const fetch = stubFetch({
            "GET /api/runs/live": () => ({ status: 200, body: view() }),
            "GET /api/runs/stats": () => ({
                status: 200,
                body: {
                    days: 30,
                    inferences_per_day: {},
                    cost_by_role: {},
                    cost_by_model: {},
                    failed_tool_calls: { total: 0, by_tool: {} },
                    cost_estimated: false,
                    budget: { period: "2026-10", month_spent: 1, monthly_budget: 30, max_run_cost: 2 },
                },
            }),
            "GET /api/runs": () => ({
                status: 200,
                body: {
                    total: 1,
                    limit: 50,
                    offset: 0,
                    runs: [
                        {
                            run_id: "run-abcdef12",
                            parent_run_id: null,
                            session_id: "s",
                            role: "user",
                            status: "completed",
                            task: "Accendi la luce",
                            created_at: "2026-10-25T10:00:00",
                            updated_at: null,
                            error: null,
                            usage: { ...EMPTY_USAGE, cost: 0.02, active_seconds: 75 },
                        },
                    ],
                },
            }),
        });

        render(<RunsPage />);

        expect(await screen.findByRole("cell", { name: "completata" })).toBeInTheDocument();
        expect(screen.getByRole("cell", { name: "1:15" })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "run-abcd" })).toHaveAttribute("href", "/control-plane/runs/view?id=run-abcdef12");

        act(() => {
            fireEvent.change(screen.getByRole("combobox", { name: "Stato" }), { target: { value: "cancelled" } });
        });

        await waitFor(() => {
            const urls = fetch.mock.calls.map(([url]) => new URL(String(url)));
            expect(urls.some((url) => url.pathname === "/api/runs" && url.searchParams.get("status") === "cancelled")).toBe(true);
        });
    });
});
