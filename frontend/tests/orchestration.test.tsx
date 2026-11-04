import { fireEvent, render, screen, within } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";

import RunsPage from "@/app/control-plane/runs/page";
import RunDetailView, { type RunDetail } from "@/components/control-plane/RunDetailView";
import RunTimeline from "@/components/control-plane/RunTimeline";
import Nucleo from "@/components/nucleo/Nucleo";
import { attemptText, describe as describeEvent, roleName, type EngineEvent } from "@/lib/nucleo/engine";
import { EMPTY_USAGE, meters, toUsage, treeRows, type TrackedRun } from "@/lib/nucleo/runs";

import { installEventSource, stubFetch } from "./helpers";

const LIMITS = {
    max_run_cost: 2,
    max_run_seconds: 900,
    max_failed_tool_calls: 10,
    max_files_modified: 20,
    max_subagents: 3,
    monthly_budget: 30,
};

function engine(event_type: string, extra: Partial<EngineEvent> = {}): EngineEvent {
    return { event_type, run_id: "run-1234", timestamp: "2026-11-04T10:00:00", ...extra };
}

function tracked(extra: Partial<TrackedRun> = {}): TrackedRun {
    return {
        id: "run-1",
        parentId: null,
        task: null,
        status: "running",
        usage: { ...EMPTY_USAGE, subagents: 1 },
        usageAt: 0,
        startedAt: 0,
        endedAt: null,
        steps: [],
        ...extra,
    };
}

function detail(extra: Partial<RunDetail> = {}): RunDetail {
    return {
        run_id: "run-parent",
        parent_run_id: null,
        session_id: "s1",
        principal_id: "u1",
        role: "admin",
        status: "completed",
        created_at: "2026-11-04T10:00:00",
        updated_at: "2026-11-04T10:01:00",
        task: { description: "Delegate the summary.", role: "architect" },
        attempts: 1,
        turn: 2,
        result: "Done.",
        error: null,
        errors: [],
        usage: { cost: 0.5, model_calls: 2, tool_calls: 1, total_tokens: 900, subagents: 1, subagent_cost: 0.2 },
        untrusted_context: true,
        exposed_tools: null,
        pending_tool_call: null,
        queued_tool_calls: [],
        last_feedback: null,
        observations: [],
        audit: [],
        subagents: [
            {
                run_id: "run-child-1",
                role: "research",
                status: "completed",
                task: "Summarise the notes.",
                cost: 0.2,
                created_at: "2026-11-04T10:00:10",
            },
        ],
        ...extra,
    };
}

describe("the Critic's verdicts", () => {
    it("say which attempt out of how many, and why", () => {
        const rejected = engine("checker.rejected", {
            attempt: 1,
            details: { max_attempts: 3, retry_instruction: "Answer in one word." },
        });
        expect(describeEvent(rejected)).toMatchObject({
            detail: "tentativo 1 di 3 · respinto · Answer in one word.",
            kind: "critic",
        });
        expect(describeEvent(engine("checker.accepted", { attempt: 2, details: { max_attempts: 3 } })).detail).toBe(
            "tentativo 2 di 3 · accettato",
        );
        expect(describeEvent(engine("retry.requested", { attempt: 2, details: { max_attempts: 3 } })).detail).toBe(
            "tentativo 2 di 3",
        );

        const failed = describeEvent(engine("checker.failed", { attempt: 1, details: { max_attempts: 3, reason: "Cannot be fixed." } }));
        expect(failed).toMatchObject({ detail: "tentativo 1 di 3 · bocciato · Cannot be fixed.", kind: "deny" });

        // An older event without the attempt still reads.
        expect(attemptText(engine("checker.accepted"))).toBe("");
        expect(describeEvent(engine("checker.accepted")).detail).toBe("accettato");
    });

    it("show in the run timeline", () => {
        render(
            <RunTimeline
                timeline={{
                    run_id: "run-1234",
                    truncated: false,
                    limits: LIMITS,
                    events: [
                        engine("run.started", { role: "research" }),
                        engine("checker.rejected", { attempt: 1, details: { max_attempts: 3, retry_instruction: "Be brief." } }),
                        engine("checker.accepted", { attempt: 2, details: { max_attempts: 3 } }),
                    ],
                }}
            />,
        );

        expect(screen.getByText("run run- · ruolo Research")).toBeInTheDocument();
        expect(screen.getByText("tentativo 1 di 3 · respinto · Be brief.")).toBeInTheDocument();
        expect(screen.getByText("tentativo 2 di 3 · accettato")).toBeInTheDocument();
    });
});

describe("the run tree", () => {
    it("puts each subagent right after its parent, oldest first", () => {
        const runs = [
            { run_id: "c2", parent_run_id: "p", created_at: "2026-11-04T10:02:00" },
            { run_id: "c1", parent_run_id: "p", created_at: "2026-11-04T10:01:00" },
            { run_id: "p", parent_run_id: null, created_at: "2026-11-04T10:00:00" },
            { run_id: "orphan", parent_run_id: "gone", created_at: "2026-11-04T09:00:00" },
            { run_id: "old", parent_run_id: null, created_at: "2026-11-04T08:00:00" },
        ];

        expect(treeRows(runs, (run) => run.created_at).map(({ run, depth }) => `${run.run_id}:${depth}`)).toEqual([
            "p:0",
            "c1:1",
            "c2:1",
            "orphan:0",
            "old:0",
        ]);
    });

    it("counts the subagents of a run that may delegate", () => {
        const byKey = (run: TrackedRun, limits = LIMITS) => Object.fromEntries(meters(run, limits, 0).map((item) => [item.key, item]));

        expect(byKey(tracked()).subagents).toMatchObject({ text: "1 / 3", level: "ok" });
        // A subagent cannot delegate, and with the limit at 0 nobody can.
        expect(byKey(tracked({ parentId: "run-0" })).subagents).toBeUndefined();
        expect(byKey(tracked(), { ...LIMITS, max_subagents: 0 }).subagents).toBeUndefined();
        expect(toUsage({ subagents: 2, subagent_cost: 0.3 })).toMatchObject({ subagents: 2, subagent_cost: 0.3 });
        expect(roleName("fast_worker")).toBe("Fast Worker");
        expect(roleName(null)).toBe("");
    });

    it("lists the subagents and the chosen role of a run", () => {
        render(<RunDetailView run={detail()} />);

        expect(screen.getByText("Architect, scelto per il comando")).toBeInTheDocument();
        expect(screen.getByText(/1 sub-agenti per \$0\.2000/)).toBeInTheDocument();

        const list = screen.getByRole("list", { name: "Sub-agenti della run" });
        expect(within(list).getByRole("link", { name: "run-chil" })).toHaveAttribute(
            "href",
            "/control-plane/runs/view?id=run-child-1",
        );
        expect(within(list).getByText("Research")).toBeInTheDocument();
        expect(within(list).getByText("Summarise the notes.")).toBeInTheDocument();
    });

    it("says who chose the role of a subagent, and when nobody did", () => {
        const { unmount } = render(
            <RunDetailView run={detail({ parent_run_id: "run-parent", task: { description: "x", role: "research" }, subagents: [] })} />,
        );
        expect(screen.getByText("Research, scelto dalla run padre")).toBeInTheDocument();
        expect(screen.queryByRole("list", { name: "Sub-agenti della run" })).not.toBeInTheDocument();
        unmount();

        render(<RunDetailView run={detail({ task: { description: "x" }, subagents: [] })} />);
        expect(screen.getByText("scelto dal triage")).toBeInTheDocument();
    });

    it("shows the history as a tree", async () => {
        installEventSource();
        const row = (run_id: string, parent_run_id: string | null, created_at: string, chosen_role: string | null) => ({
            run_id,
            parent_run_id,
            session_id: "s",
            role: "admin",
            chosen_role,
            status: "completed",
            task: `task ${run_id}`,
            created_at,
            updated_at: null,
            error: null,
            usage: EMPTY_USAGE,
        });
        stubFetch({
            "GET /api/runs/live": () => ({ status: 200, body: { halted: false, halt_reason: null, limits: LIMITS, runs: [] } }),
            "GET /api/runs/stats": () => ({
                status: 200,
                body: {
                    days: 30,
                    inferences_per_day: {},
                    cost_by_role: {},
                    cost_by_model: {},
                    failed_tool_calls: { total: 0, by_tool: {} },
                    cost_estimated: false,
                    budget: { period: "2026-11", month_spent: 0, monthly_budget: 30, max_run_cost: 2 },
                },
            }),
            "GET /api/runs": () => ({
                status: 200,
                body: {
                    total: 3,
                    limit: 50,
                    offset: 0,
                    runs: [
                        row("run-child000", "run-parent0", "2026-11-04T10:01:00", "research"),
                        row("run-parent0", null, "2026-11-04T10:00:00", "architect"),
                        row("run-other00", null, "2026-11-04T09:00:00", null),
                    ],
                },
            }),
        });

        render(<RunsPage />);

        await screen.findByRole("link", { name: "run-chil" });
        const links = screen.getAllByRole("link").map((link) => link.textContent);
        expect(links.filter((text) => text?.startsWith("run-"))).toEqual(["run-pare", "run-chil", "run-othe"]);
        expect(screen.getByText("sub-agente · Research")).toBeInTheDocument();
        expect(screen.getByText("ruolo Architect")).toBeInTheDocument();
    });
});

describe("the role of one command", () => {
    it("is sent with the command when chosen", async () => {
        installEventSource();
        const fetch = stubFetch({
            "GET /api/approvals": () => ({ status: 200, body: [] }),
            "GET /api/runs/stats": () => ({ status: 200, body: { budget: { month_spent: 0, monthly_budget: 2 } } }),
            "GET /api/runs/live": () => ({ status: 200, body: { halted: false, halt_reason: null, limits: LIMITS, runs: [] } }),
            "POST /api/orchestrator/ask": () => ({ status: 200, body: { transcription: "Fatto.", audio_base64: "" } }),
        });

        render(<Nucleo />);
        const select = screen.getByRole("combobox", { name: "Ruolo del comando" });
        expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual([
            "auto",
            "Architect",
            "Research",
            "Fast Worker",
            "Triage",
        ]);

        fireEvent.change(screen.getByRole("textbox", { name: "Comando" }), { target: { value: "Prima" } });
        fireEvent.click(screen.getByRole("button", { name: "INVIA" }));
        await screen.findByText("Fatto.");

        fireEvent.change(select, { target: { value: "research" } });
        fireEvent.change(screen.getByRole("textbox", { name: "Comando" }), { target: { value: "Seconda" } });
        fireEvent.click(screen.getByRole("button", { name: "INVIA" }));
        await screen.findByText("Seconda");

        const forms = fetch.mock.calls
            .filter(([url]) => String(url).endsWith("/api/orchestrator/ask"))
            .map(([, init]) => init?.body as FormData);
        expect(forms.map((form) => [form.get("text"), form.get("role")])).toEqual([
            ["Prima", null],
            ["Seconda", "research"],
        ]);
    });
});
