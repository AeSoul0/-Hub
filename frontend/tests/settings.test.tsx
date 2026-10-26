import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import SettingsPage from "@/app/control-plane/settings/page";
import SetupPage from "@/app/control-plane/setup/page";
import RoleEditor from "@/components/control-plane/RoleEditor";
import SettingsForm from "@/components/control-plane/SettingsForm";
import { IssueList, PriceTable, SecretList } from "@/components/control-plane/SettingsPanels";
import { ApiError, putJson } from "@/lib/api/client";
import { mergePrices, type RoleName, type SettingField, type SettingsView } from "@/lib/api/settings";
import { criticConflicts, emptyRoles, parseTarget, rolesJson, type Chains } from "@/lib/nucleo/models";

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

const DEFAULT_ROLES: SettingsView["roles"] = {
    architect: { chain: ["openai:gpt-5.5"], custom: false },
    research: { chain: ["openai:gpt-5.5"], custom: false },
    critic: { chain: ["openai:gpt-5.5-critic"], custom: false },
    fast_worker: { chain: ["openai:gpt-5.5"], custom: false },
    triage: { chain: ["openai:gpt-5.5"], custom: false },
};

export function view(overrides: Partial<SettingsView> = {}): SettingsView {
    return {
        settings: [
            field({ name: "OPENAI_MODEL", group: "models", label: "Worker model", kind: "text", value: "gpt-5.5" }),
            field({ name: "AEHUB_CHECKER_MODEL", group: "models", label: "Critic model", kind: "text", value: "" }),
            field({ name: "AEHUB_MODEL_ROLES", group: "models", label: "Role routing", kind: "roles", value: "" }),
            field({
                name: "AEHUB_FORCE_ROLE",
                group: "models",
                label: "Forced role",
                kind: "choice",
                default: "",
                value: "",
                options: ["architect", "research", "fast_worker", "triage"],
            }),
            field({ name: "AEHUB_MODEL_PRICES", group: "prices", label: "Model prices", kind: "prices", value: "" }),
            field({ name: "AEHUB_MONTHLY_BUDGET", label: "Monthly budget (USD)", value: "30.0" }),
            field(),
            field({ name: "AEHUB_BUDGET_WARNING_RATIO", label: "Budget warning threshold", kind: "ratio", value: "0.8" }),
            field({ name: "AEHUB_BREAKER_THRESHOLD", group: "engine", label: "Failures", kind: "integer", value: "3", default: "3" }),
        ],
        secrets: [
            { name: "OPENAI_API_KEY", label: "OpenAI API key", used_for: "models with the openai provider", configured: true },
            { name: "OPENROUTER_API_KEY", label: "OpenRouter API key", used_for: "models with the openrouter provider", configured: false },
        ],
        issues: [],
        models: [{ model: "gpt-5.5", providers: ["openai"], roles: ["architect"], priced: false }],
        roles: DEFAULT_ROLES,
        providers: {
            openai: { key: true, needs_key: true },
            openrouter: { key: false, needs_key: true },
            local: { key: false, needs_key: false, base_url: "http://localhost:11434/v1" },
        },
        workspace: { path: "/app/workspace", exists: true },
        ready: true,
        onboarding: { completed: false, completed_at: null },
        ...overrides,
    };
}

const CATALOG = {
    "GET /api/settings/provider-models/openai": () => ({ status: 200, body: { provider: "openai", models: [] } }),
    "GET /api/settings/provider-models/openrouter": () => ({
        status: 200,
        body: {
            provider: "openrouter",
            models: [
                {
                    id: "anthropic/claude-sonnet-5.5",
                    name: "Claude Sonnet 5.5",
                    context: 200000,
                    price: { input: 3, output: 15 },
                },
            ],
        },
    }),
    "GET /api/settings/provider-models/local": () => ({ status: 503, body: { detail: "not reachable" } }),
    "GET /api/desktop": () => ({ status: 200, body: { desktop: false } }),
};

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

        expect(screen.getByText("predefinito")).toBeInTheDocument();
        expect(screen.getByText("da backend/.env")).toBeInTheDocument();

        const save = screen.getByRole("button", { name: "Salva" });
        expect(save).toBeDisabled();

        fireEvent.change(screen.getByLabelText("Costo massimo di una run (USD)"), { target: { value: "0.5" } });
        fireEvent.click(save);

        expect(onSave).toHaveBeenCalledWith({ AEHUB_RUN_MAX_COST: "0.5" });
    });

    it("resets a stored value, shows field errors and offers the choices", () => {
        const onSave = vi.fn();
        render(
            <SettingsForm
                fields={[
                    field({ value: "0.5", source: "database" }),
                    view().settings.find((entry) => entry.name === "AEHUB_FORCE_ROLE") as SettingField,
                ]}
                errors={{ AEHUB_RUN_MAX_COST: "Enter a number." }}
                busy={false}
                onSave={onSave}
            />,
        );

        expect(screen.getByText("Enter a number.")).toBeInTheDocument();
        expect(screen.getByLabelText("Costo massimo di una run (USD)")).toHaveAttribute("aria-invalid", "true");

        const role = screen.getByLabelText("Ruolo forzato");
        expect(within(role).getByRole("option", { name: "per regole (consigliato)" })).toBeInTheDocument();
        fireEvent.change(role, { target: { value: "research" } });

        fireEvent.click(screen.getByRole("button", { name: "Ripristina Costo massimo di una run (USD)" }));
        expect(onSave).toHaveBeenCalledWith({ AEHUB_RUN_MAX_COST: null });

        fireEvent.click(screen.getByRole("button", { name: "Salva" }));
        expect(onSave).toHaveBeenLastCalledWith({ AEHUB_FORCE_ROLE: "research" });
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
        expect(items[0]).toHaveTextContent("blocca le run");
        expect(items[0]).toHaveTextContent("Critic equals Worker.");
    });

    it("shows whether a key is set, never a value, and how to add one", () => {
        render(<SecretList secrets={view().secrets} />);

        const [openai, openrouter] = screen.getAllByRole("listitem");
        expect(openai).toHaveTextContent("OpenAI");
        expect(openai).toHaveTextContent("impostata");
        expect(openrouter).toHaveTextContent("mancante");
        expect(screen.getByText("python scripts/aehub.py setup")).toBeInTheDocument();
    });

    it("builds the price table JSON and takes OpenRouter's prices", () => {
        const onSave = vi.fn();
        render(
            <PriceTable
                models={[
                    { model: "worker-model", providers: ["openai"], roles: ["triage"], priced: false },
                    { model: "anthropic/claude-sonnet-5.5", providers: ["openrouter"], roles: ["critic"], priced: false },
                ]}
                pricesJson={JSON.stringify({ "old-model": { input: 1, output: 2 } })}
                busy={false}
                catalog={{ "anthropic/claude-sonnet-5.5": { input: 3, output: 15 } }}
                onSave={onSave}
            />,
        );

        fireEvent.change(screen.getByLabelText("Prezzo input di worker-model"), { target: { value: "1.25" } });
        fireEvent.change(screen.getByLabelText("Prezzo output di worker-model"), { target: { value: "10" } });
        fireEvent.click(screen.getByRole("button", { name: "Usa i prezzi di OpenRouter (1)" }));
        expect(screen.getByLabelText("Prezzo output di anthropic/claude-sonnet-5.5")).toHaveValue("15");
        fireEvent.click(screen.getByRole("button", { name: "Salva i prezzi" }));

        const rows = onSave.mock.calls[0][0];
        expect(JSON.parse(mergePrices(JSON.stringify({ "old-model": { input: 1, output: 2 } }), rows))).toEqual({
            "old-model": { input: 1, output: 2 },
            "worker-model": { input: 1.25, output: 10 },
            "anthropic/claude-sonnet-5.5": { input: 3, output: 15 },
        });
        // Empty rows add nothing.
        expect(mergePrices("", { x: { input: "", output: "" } })).toBe("{}");
    });
});

describe("role chains", () => {
    const chains = (overrides: Partial<Record<RoleName, string[]>> = {}): Chains =>
        Object.fromEntries(
            Object.entries({ ...Object.fromEntries(Object.entries(DEFAULT_ROLES).map(([r, v]) => [r, v.chain])), ...overrides }).map(
                ([role, labels]) => [role, (labels as string[]).map(parseTarget)],
            ),
        ) as Chains;

    it("writes only the custom roles and finds a Critic shared with a worker", () => {
        const custom = { architect: false, research: false, critic: true, fast_worker: false, triage: true };
        const current = chains({ critic: ["openrouter:anthropic/claude-sonnet-5.5"], triage: ["local:llama3.3", "openai:gpt-5.5-mini"] });

        expect(JSON.parse(rolesJson(current, custom))).toEqual({
            critic: ["openrouter:anthropic/claude-sonnet-5.5"],
            triage: ["local:llama3.3", "openai:gpt-5.5-mini"],
        });
        expect(rolesJson(current, { ...custom, critic: false, triage: false })).toBe("");
        expect(criticConflicts(current)).toEqual([]);

        const clash = chains({ critic: ["openrouter:gpt-5.5"] });
        expect(criticConflicts(clash).map((entry) => entry.role)).toEqual(["architect", "research", "fast_worker", "triage"]);
        expect(emptyRoles(chains({ triage: [] }), { ...custom })).toEqual(["triage"]);
        expect(parseTarget("openrouter:meta/llama:free")).toEqual({ provider: "openrouter", model: "meta/llama:free" });
    });
});

describe("RoleEditor", () => {
    it("customises the Critic, refuses a shared model, saves the chain", async () => {
        stubFetch(CATALOG);
        const onSave = vi.fn();
        render(<RoleEditor view={view()} busy={false} onSave={onSave} />);

        const critic = screen.getByRole("region", { name: "Critic · supervisore" });
        expect(within(critic).getByText("predefinito")).toBeInTheDocument();
        expect(within(critic).getByLabelText("Modello 1 di Critic · supervisore")).toBeDisabled();
        expect(screen.getByRole("button", { name: "Salva i modelli" })).toBeDisabled();

        fireEvent.click(within(critic).getByRole("button", { name: "Personalizza" }));
        const model = within(critic).getByLabelText("Modello 1 di Critic · supervisore");
        fireEvent.change(model, { target: { value: "gpt-5.5" } });

        expect(screen.getByRole("alert")).toHaveTextContent("gpt-5.5 è anche in Architect");
        expect(screen.getByRole("button", { name: "Salva i modelli" })).toBeDisabled();

        fireEvent.change(within(critic).getByLabelText("Provider 1 di Critic · supervisore"), { target: { value: "openrouter" } });
        fireEvent.change(model, { target: { value: "anthropic/claude-sonnet-5.5" } });
        fireEvent.click(within(critic).getByRole("button", { name: "+ modello di riserva" }));
        // A fallback starts on the provider of the row above.
        const provider2 = within(critic).getByLabelText("Provider 2 di Critic · supervisore");
        expect(provider2).toHaveValue("openrouter");
        fireEvent.change(provider2, { target: { value: "openai" } });
        fireEvent.change(within(critic).getByLabelText("Modello 2 di Critic · supervisore"), { target: { value: "gpt-5.5-critic" } });
        fireEvent.click(within(critic).getByRole("button", { name: "Sposta su gpt-5.5-critic" }));

        expect(within(critic).getByText("Manca la chiave di OpenRouter.")).toBeInTheDocument();
        await waitFor(() =>
            expect(document.querySelector('#models-openrouter option[value="anthropic/claude-sonnet-5.5"]')).not.toBeNull(),
        );

        fireEvent.click(screen.getByRole("button", { name: "Salva i modelli" }));
        expect(onSave).toHaveBeenCalledWith({
            AEHUB_MODEL_ROLES: JSON.stringify({ critic: ["openai:gpt-5.5-critic", "openrouter:anthropic/claude-sonnet-5.5"] }),
        });
    });

    it("goes back to the default by saving no routing", () => {
        stubFetch(CATALOG);
        const onSave = vi.fn();
        const custom = view({
            roles: { ...DEFAULT_ROLES, triage: { chain: ["local:llama3.3"], custom: true } },
            settings: view().settings.map((entry) =>
                entry.name === "AEHUB_MODEL_ROLES" ? { ...entry, value: '{"triage": ["local:llama3.3"]}', source: "database" } : entry,
            ),
        });
        render(<RoleEditor view={custom} busy={false} onSave={onSave} />);

        const triage = screen.getByRole("region", { name: "Triage" });
        expect(within(triage).getByText("personalizzato")).toBeInTheDocument();
        fireEvent.click(within(triage).getByRole("button", { name: "torna al predefinito" }));
        fireEvent.click(screen.getByRole("button", { name: "Salva i modelli" }));

        expect(onSave).toHaveBeenCalledWith({ AEHUB_MODEL_ROLES: null });
    });
});

describe("SettingsPage", () => {
    it("shows every section and saves an engine setting", async () => {
        let current = view({ onboarding: { completed: true, completed_at: "2026-10-26T10:00:00Z" } });
        const fetch = stubFetch({
            ...CATALOG,
            "GET /api/settings": () => ({ status: 200, body: current }),
            "PUT /api/settings": () => {
                current = view({
                    onboarding: { completed: true, completed_at: "2026-10-26T10:00:00Z" },
                    settings: current.settings.map((entry) =>
                        entry.name === "AEHUB_BREAKER_THRESHOLD" ? { ...entry, value: "2", source: "database" } : entry,
                    ),
                });
                return { status: 200, body: current };
            },
        });

        render(<SettingsPage />);

        expect(await screen.findByText("IMPOSTAZIONI")).toBeInTheDocument();
        for (const title of ["Chiavi", "Modelli per ruolo", "Prezzi", "Budget e limiti", "Motore", "Cartella di lavoro"]) {
            expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
        }
        expect(screen.getByRole("region", { name: "Fast Worker" })).toBeInTheDocument();

        fireEvent.change(screen.getByLabelText("Errori prima di saltare un modello"), { target: { value: "2" } });
        const engine = screen.getByRole("heading", { name: "Motore" }).parentElement as HTMLElement;
        fireEvent.click(within(engine).getByRole("button", { name: "Salva" }));

        expect(await screen.findByText("Salvato: la prossima run usa queste impostazioni.")).toBeInTheDocument();
        const put = fetch.mock.calls.find(([, init]) => init?.method === "PUT");
        expect(JSON.parse(String(put?.[1]?.body))).toEqual({ values: { AEHUB_BREAKER_THRESHOLD: "2" } });
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
            ...CATALOG,
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

        expect(await screen.findByText("PRIMO AVVIO")).toBeInTheDocument();
        expect(screen.getByText("OpenAI")).toBeInTheDocument();

        // Models: the Critic is set, the API accepts it, the wizard moves on.
        fireEvent.click(screen.getByRole("button", { name: "Continua" }));
        fireEvent.change(await screen.findByLabelText("Critic predefinito"), { target: { value: "critic-model" } });
        fireEvent.click(screen.getByRole("button", { name: "Salva e continua" }));

        await waitFor(() => expect(screen.getByRole("button", { name: "Salta per ora" })).toBeInTheDocument());
        const put = fetch.mock.calls.find(([, init]) => init?.method === "PUT");
        expect(JSON.parse(String(put?.[1]?.body))).toEqual({ values: { AEHUB_CHECKER_MODEL: "critic-model" } });

        fireEvent.click(screen.getByRole("button", { name: "5. Controllo" }));
        const finish = screen.getByRole("button", { name: "Finisci il primo avvio" });
        expect(finish).toBeEnabled();
        fireEvent.click(finish);

        expect(await screen.findByText("PRIMO AVVIO COMPLETATO")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Apri il Nucleo" })).toHaveAttribute("href", "/");
    });

    it("keeps Finish disabled while an error blocks runs", async () => {
        stubFetch({
            ...CATALOG,
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

        fireEvent.click(await screen.findByRole("button", { name: "5. Controllo" }));
        expect(screen.getByRole("button", { name: "Finisci il primo avvio" })).toBeDisabled();
        expect(screen.getByText(/OPENAI_API_KEY is not set/)).toBeInTheDocument();
    });
});
