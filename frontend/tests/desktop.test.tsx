import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DesktopKeys from "@/components/control-plane/DesktopKeys";
import type { SecretStatus } from "@/lib/api/settings";
import { runHref } from "@/lib/routes";

import { stubFetch } from "./helpers";

const SECRETS: SecretStatus[] = [
    { name: "OPENAI_API_KEY", label: "OpenAI API key", used_for: "openai", configured: true },
    { name: "OPENROUTER_API_KEY", label: "OpenRouter API key", used_for: "openrouter", configured: false },
    { name: "AEHUB_LOCAL_API_KEY", label: "Local server key", used_for: "local", configured: false },
];

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("DesktopKeys", () => {
    it("sends only the keys typed, then forgets them", async () => {
        const fetch = stubFetch({
            "PUT /api/desktop/secrets": () => ({ status: 200, body: { saved: ["OPENROUTER_API_KEY"] } }),
        });
        const onSaved = vi.fn();
        render(<DesktopKeys secrets={SECRETS} onSaved={onSaved} />);

        expect(screen.getByLabelText("Server locale")).toBeInTheDocument();
        expect(screen.getByLabelText("OpenAI")).toHaveAttribute("placeholder", "sostituisci");
        const input = screen.getByLabelText("OpenRouter") as HTMLInputElement;
        expect(input.type).toBe("password");
        fireEvent.change(input, { target: { value: "sk-or-test" } });
        fireEvent.click(screen.getByRole("button", { name: "Salva le chiavi" }));

        await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
        const [, init] = fetch.mock.calls[0];
        expect(JSON.parse(String(init?.body))).toEqual({ OPENROUTER_API_KEY: "sk-or-test" });
        expect(input.value).toBe("");
        expect(screen.getByText("Salvate nel portachiavi del sistema.")).toBeInTheDocument();
    });

    it("shows the backend's refusal", async () => {
        stubFetch({
            "PUT /api/desktop/secrets": () => ({ status: 404, body: { detail: "Keys are set with the launcher" } }),
        });
        const onSaved = vi.fn();
        render(<DesktopKeys secrets={SECRETS} onSaved={onSaved} />);

        fireEvent.change(screen.getByLabelText("OpenAI"), { target: { value: "sk-1" } });
        fireEvent.click(screen.getByRole("button", { name: "Salva le chiavi" }));

        expect(await screen.findByText("Keys are set with the launcher")).toBeInTheDocument();
        expect(onSaved).not.toHaveBeenCalled();
    });
});

describe("runHref", () => {
    it("puts the id in the query string, encoded", () => {
        expect(runHref("run 1/2")).toBe("/control-plane/runs/view?id=run%201%2F2");
    });
});
