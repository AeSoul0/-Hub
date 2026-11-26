/**
 * @file frontend/tests/instant.test.tsx
 * @description Instant commands (V1, ADR-035): the Nucleo marks a reply that came without the model, and Settings edits the app list row by row.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AppListEditor, { appRows, splitArgs } from "@/components/control-plane/AppListEditor";
import Nucleo from "@/components/nucleo/Nucleo";
import { chooseLanguage } from "@/lib/i18n";

import { installEventSource, stubFetch } from "./helpers";

const LIMITS = {
    max_run_cost: 2,
    max_run_seconds: 900,
    max_failed_tool_calls: 10,
    max_files_modified: 20,
    max_subagents: 3,
    monthly_budget: 30,
};

function nucleo(reply: Record<string, unknown>) {
    installEventSource();
    stubFetch({
        "GET /api/approvals": () => ({ status: 200, body: [] }),
        "GET /api/runs/stats": () => ({
            status: 200,
            body: { budget: { month_spent: 0, monthly_budget: 2 } },
        }),
        "GET /api/runs/live": () => ({
            status: 200,
            body: { halted: false, halt_reason: null, limits: LIMITS, runs: [] },
        }),
        "POST /api/orchestrator/ask": () => ({ status: 200, body: reply }),
    });
    render(<Nucleo />);
}

describe("an instant command in the Nucleo", () => {
    beforeEach(() => chooseLanguage("it"));

    it("says it ran at once, and how fast", async () => {
        nucleo({
            transcription: "Apro Spotify.",
            audio_base64: "",
            instant: { tool: "open_app", ms: 8, success: true },
        });

        fireEvent.change(screen.getByRole("textbox", { name: "Comando" }), {
            target: { value: "apri spotify" },
        });
        fireEvent.click(screen.getByRole("button", { name: "INVIA" }));

        expect(await screen.findByText("Apro Spotify.")).toBeInTheDocument();
        expect(screen.getByText(/istantaneo · 8 ms/)).toBeInTheDocument();
    });

    it("marks nothing when the engine answered", async () => {
        nucleo({ transcription: "Domani piove.", audio_base64: "" });

        fireEvent.change(screen.getByRole("textbox", { name: "Comando" }), {
            target: { value: "che tempo fa?" },
        });
        fireEvent.click(screen.getByRole("button", { name: "INVIA" }));

        expect(await screen.findByText("Domani piove.")).toBeInTheDocument();
        expect(screen.queryByText(/istantaneo/)).not.toBeInTheDocument();
    });
});

describe("the app list in Settings", () => {
    beforeEach(() => chooseLanguage("en"));

    it("reads the stored list into rows and saves rows back as the JSON the backend reads", () => {
        expect(
            appRows('{"spotify": "spotify", "code": ["code", "--new-window", "my project"]}')
        ).toEqual([
            { name: "spotify", program: "spotify", args: "" },
            { name: "code", program: "code", args: '--new-window "my project"' },
        ]);
        expect(appRows("not json")).toEqual([]);
        expect(splitArgs('--a "b c" d')).toEqual(["--a", "b c", "d"]);

        const onSave = vi.fn();
        render(<AppListEditor value='{"spotify": "spotify"}' busy={false} onSave={onSave} />);

        fireEvent.click(screen.getByRole("button", { name: "Add an app" }));
        const names = screen.getAllByLabelText("Name you say");
        const programs = screen.getAllByLabelText("Program, path or link");
        fireEvent.change(names[1], { target: { value: "Code" } });
        fireEvent.change(programs[1], { target: { value: "code" } });
        fireEvent.change(screen.getAllByLabelText("Arguments (optional)")[1], {
            target: { value: '--new-window "my project"' },
        });
        fireEvent.click(screen.getByRole("button", { name: "Save apps" }));

        expect(onSave).toHaveBeenCalledWith(
            '{"spotify":"spotify","Code":["code","--new-window","my project"]}'
        );
    });

    it("refuses an incomplete row or a name used twice, and removes a row", () => {
        const onSave = vi.fn();
        render(<AppListEditor value='{"spotify": "spotify"}' busy={false} onSave={onSave} />);

        fireEvent.click(screen.getByRole("button", { name: "Add an app" }));
        fireEvent.click(screen.getByRole("button", { name: "Save apps" }));
        expect(screen.getByRole("alert")).toHaveTextContent(
            "Every row needs a name and a program."
        );

        fireEvent.change(screen.getAllByLabelText("Name you say")[1], {
            target: { value: "Spotify" },
        });
        fireEvent.change(screen.getAllByLabelText("Program, path or link")[1], {
            target: { value: "x" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Save apps" }));
        expect(screen.getByRole("alert")).toHaveTextContent("Two apps have the same name.");
        expect(onSave).not.toHaveBeenCalled();

        fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[1]);
        fireEvent.click(screen.getByRole("button", { name: "Save apps" }));
        expect(onSave).toHaveBeenCalledWith('{"spotify":"spotify"}');
    });
});
