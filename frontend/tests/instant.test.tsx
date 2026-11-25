/**
 * @file frontend/tests/instant.test.tsx
 * @description Instant commands (V1, ADR-035): the Nucleo marks a reply that came without the model, and Settings edits the app list.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsForm from "@/components/control-plane/SettingsForm";
import Nucleo from "@/components/nucleo/Nucleo";
import { chooseLanguage } from "@/lib/i18n";
import type { SettingField } from "@/lib/api/settings";

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
        "GET /api/runs/stats": () => ({ status: 200, body: { budget: { month_spent: 0, monthly_budget: 2 } } }),
        "GET /api/runs/live": () => ({ status: 200, body: { halted: false, halt_reason: null, limits: LIMITS, runs: [] } }),
        "POST /api/orchestrator/ask": () => ({ status: 200, body: reply }),
    });
    render(<Nucleo />);
}

describe("an instant command in the Nucleo", () => {
    beforeEach(() => chooseLanguage("it"));

    it("says it ran at once, and how fast", async () => {
        nucleo({ transcription: "Apro Spotify.", audio_base64: "", instant: { tool: "open_app", ms: 8, success: true } });

        fireEvent.change(screen.getByRole("textbox", { name: "Comando" }), { target: { value: "apri spotify" } });
        fireEvent.click(screen.getByRole("button", { name: "INVIA" }));

        expect(await screen.findByText("Apro Spotify.")).toBeInTheDocument();
        expect(screen.getByText(/istantaneo · 8 ms/)).toBeInTheDocument();
    });

    it("marks nothing when the engine answered", async () => {
        nucleo({ transcription: "Domani piove.", audio_base64: "" });

        fireEvent.change(screen.getByRole("textbox", { name: "Comando" }), { target: { value: "che tempo fa?" } });
        fireEvent.click(screen.getByRole("button", { name: "INVIA" }));

        expect(await screen.findByText("Domani piove.")).toBeInTheDocument();
        expect(screen.queryByText(/istantaneo/)).not.toBeInTheDocument();
    });
});

describe("the app list in Settings", () => {
    beforeEach(() => chooseLanguage("en"));

    it("is a multi-line field, saved as written", () => {
        const field: SettingField = {
            name: "AEHUB_APPS",
            group: "engine",
            label: "Apps ÆHub may open",
            kind: "apps",
            help: "",
            default: "",
            value: "",
            source: "default",
        };
        const onSave = vi.fn();
        render(<SettingsForm fields={[field]} errors={{}} busy={false} onSave={onSave} />);

        const box = screen.getByLabelText("Apps ÆHub may open");
        expect(box.tagName).toBe("TEXTAREA");
        fireEvent.change(box, { target: { value: '{"spotify": "spotify"}' } });
        fireEvent.submit(box.closest("form")!);

        expect(onSave).toHaveBeenCalledWith({ AEHUB_APPS: '{"spotify": "spotify"}' });
    });
});
