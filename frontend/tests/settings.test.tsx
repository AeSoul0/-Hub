import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import SetupPage from "@/app/control-plane/setup/page";
import SettingsForm from "@/components/control-plane/SettingsForm";
import { IssueList, PriceTable, SecretList } from "@/components/control-plane/SettingsPanels";
import { ApiError, putJson } from "@/lib/api/client";
import { mergePrices, type SettingField, type SettingsView } from "@/lib/api/settings";

import { stubFetch } from "./helpers";

vi.mock("next/link", () => ({
    default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
        <a href={href} {...rest}>
            {children}
        </a>
    ),
}));

function field(overrides: Partial<SettingField> = {}): SettingField {
    return {
        name: "AEHUB_RUN_MAX_COST",
        group: "limits",
        label: "Maximum cost of one run (USD)",
        kind: "number",
        help: "The run stops when it reaches this cost.",
        default: "2.0",
        value: "2.0",
        source: "default",
        ...overrides,
    };
}

function view(overrides: Partial<SettingsView> = {}): SettingsView {
    return {
        settings: [
            field({ name: "OPENAI_MODEL", group: "models", label: "Worker model", kind: "text", value: "gpt-5.5" }),
            field({ name: "AEHUB_CHECKER_MODEL", group: "models", label: "Critic model", kind: "text", value: "" }),
            field({ name: "AEHUB_MODEL_ROLES", group: "models", label: "Role routing", kind: "roles", value: "" }),
            field({ name: "AEHUB_MODEL_PRICES", group: "prices", label: "Model prices", kind: "prices", value: "" }),
            field({ name: "AEHUB_MONTHLY_BUDGET", label: "Monthly budget (USD)", value: "30.0" }),
            field(),
            field({ name: "AEHUB_BUDGET_WARNING_RATIO", label: "Budget warning threshold", kind: "ratio", value: "0.8" }),
        ],
        secrets: [
            { name: "OPENAI_API_KEY", label: "OpenAI API key", used_for: "models with the openai provider", configured: true },
            { name: "GROQ_API_KEY", label: "Groq API key", used_for: "voice transcription", configured: false },
        ],
        issues: [],
        models: [],
        workspace: { path: "/app/workspace", exists: true },
        ready: true,
        onboarding: { completed: false, completed_at: null },
        ...overrides,
    };
}

describe("SettingsForm", () => {
    it("saves only what changed and shows where each value comes from", () => {
        const onSave = vi.fn();
        render(
            <SettingsForm
                fields={[field(), field({ name: "AEHUB_MONTHLY_BUDGET", label: "Monthly budget", value: "30", source: "environment" })]}
                errors={{}}
                busy={false}
                onSave={onSave}
            />,
        );

        expect(screen.getByText("default")).toBeInTheDocument();
        expect(screen.getByText("from backend/.env")).toBeInTheDocument();

        const save = screen.getByRole("button", { name: "Save" });
        expect(save).toBeDisabled();

        fireEvent.change(screen.getByLabelText("Maximum cost of one run (USD)"), { target: { value: "0.5" } });
        fireEvent.click(save);

        expect(onSave).toHaveBeenCalledWith({ AEHUB_RUN_MAX_COST: "0.5" });
    });

    it("resets a stored value and shows field errors", () => {
        const onSave = vi.fn();
        render(
            <SettingsForm
                fields={[field({ value: "0.5", source: "database" })]}
                errors={{ AEHUB_RUN_MAX_COST: "Enter a number." }}
                busy={false}
                onSave={onSave}
            />,
        );

        expect(screen.getByText("Enter a number.")).toBeInTheDocument();
        expect(screen.getByLabelText("Maximum cost of one run (USD)")).toHaveAttribute("aria-invalid", "true");

        fireEvent.click(screen.getByRole("button", { name: "Reset Maximum cost of one run (USD)" }));
        expect(onSave).toHaveBeenCalledWith({ AEHUB_RUN_MAX_COST: null });
    });
});

describe("Settings panels", () => {
    it("lists blocking issues first", () => {
        render(
            <IssueList
                issues={[
                    { code: "voice_disabled", severity: "info", message: "Voice input is off.", setting: null },
                    { code: "routing_invalid", severity: "error", message: "Critic equals Worker.", setting: null },
                ]}
            />,
        );

        const items = screen.getAllByRole("listitem");
        expect(items[0]).toHaveTextContent("Blocks runs");
        expect(items[0]).toHaveTextContent("Critic equals Worker.");
    });

    it("shows whether a key is set, never a value, and how to add one", () => {
        render(<SecretList secrets={view().secrets} />);

        expect(screen.getByText("OPENAI_API_KEY").previousSibling).toHaveTextContent("set");
        expect(screen.getByText("GROQ_API_KEY").previousSibling).toHaveTextContent("not set");
        expect(screen.getByText("python scripts/aehub.py setup")).toBeInTheDocument();
    });

    it("builds the price table JSON, keeping other models", () => {
        const onSave = vi.fn();
        render(
            <PriceTable
                models={[{ model: "worker-model", providers: ["openai"], roles: ["triage"], priced: false }]}
                pricesJson={JSON.stringify({ "old-model": { input: 1, output: 2 } })}
                busy={false}
                onSave={onSave}
            />,
        );

        fireEvent.change(screen.getByLabelText("worker-model input price"), { target: { value: "1.25" } });
        fireEvent.change(screen.getByLabelText("worker-model output price"), { target: { value: "10" } });
        fireEvent.click(screen.getByRole("button", { name: "Save prices" }));

        const rows = onSave.mock.calls[0][0];
        expect(JSON.parse(mergePrices(JSON.stringify({ "old-model": { input: 1, output: 2 } }), rows))).toEqual({
            "old-model": { input: 1, output: 2 },
            "worker-model": { input: 1.25, output: 10 },
        });
        // Empty rows add nothing.
        expect(mergePrices("", { "x": { input: "", output: "" } })).toBe("{}");
    });
});

describe("Settings API errors", () => {
    it("carries the per-field errors of a refused save", async () => {
        stubFetch({
            "PUT /api/settings": () => ({
                status: 422,
                body: { detail: { message: "Settings not saved.", errors: { AEHUB_MONTHLY_BUDGET: "Enter a number." } } },
            }),
        });

        const error = (await putJson("/api/settings", { values: {} }).catch((err: unknown) => err)) as ApiError;

        expect(error).toBeInstanceOf(ApiError);
        expect(error.status).toBe(422);
        expect(error.message).toBe("Settings not saved.");
        expect(error.errors).toEqual({ AEHUB_MONTHLY_BUDGET: "Enter a number." });
    });
});

describe("First-run setup", () => {
    it("walks to the check, refuses while runs are blocked, then finishes", async () => {
        let current = view({
            ready: false,
            issues: [{ code: "routing_invalid", severity: "error", message: "Critic equals Worker.", setting: null }],
        });

        const fetch = stubFetch({
            "GET /api/settings": () => ({ status: 200, body: current }),
            "PUT /api/settings": () => {
                current = view();
                return { status: 200, body: current };
            },
            "POST /api/settings/onboarding": () => {
                current = view({ onboarding: { completed: true, completed_at: "2026-10-23T15:00:00Z" } });
                return { status: 200, body: current };
            },
        });

        render(<SetupPage />);

        expect(await screen.findByText("First-run setup")).toBeInTheDocument();
        expect(screen.getByText("OPENAI_API_KEY")).toBeInTheDocument();

        // Models: the Critic is set, the API accepts it, the wizard moves on.
        fireEvent.click(screen.getByRole("button", { name: "Continue" }));
        fireEvent.change(await screen.findByLabelText("Critic model"), { target: { value: "critic-model" } });
        fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));

        await waitFor(() => expect(screen.getByRole("button", { name: "Skip for now" })).toBeInTheDocument());
        const put = fetch.mock.calls.find(([, init]) => init?.method === "PUT");
        expect(JSON.parse(String(put?.[1]?.body))).toEqual({ values: { AEHUB_CHECKER_MODEL: "critic-model" } });

        fireEvent.click(screen.getByRole("button", { name: "5. Check" }));
        const finish = screen.getByRole("button", { name: "Finish setup" });
        expect(finish).toBeEnabled();
        fireEvent.click(finish);

        expect(await screen.findByText("Setup complete")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Open the assistant" })).toHaveAttribute("href", "/");
    });

    it("keeps Finish disabled while an error blocks runs", async () => {
        stubFetch({
            "GET /api/settings": () => ({
                status: 200,
                body: view({
                    ready: false,
                    issues: [
                        { code: "provider_key_missing", severity: "error", message: "OPENAI_API_KEY is not set.", setting: null },
                    ],
                }),
            }),
        });

        render(<SetupPage />);

        fireEvent.click(await screen.findByRole("button", { name: "5. Check" }));
        expect(screen.getByRole("button", { name: "Finish setup" })).toBeDisabled();
        expect(screen.getByText(/OPENAI_API_KEY is not set/)).toBeInTheDocument();
    });
});
