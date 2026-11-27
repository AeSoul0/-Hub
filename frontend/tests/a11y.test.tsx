/**
 * @file frontend/tests/a11y.test.tsx
 * @description N6: accessibility checked automatically (axe-core) on the
 * Nucleo, its history, the first start, the trash and the login, in both
 * languages; and the contrast of the palette's text colors (WCAG AA, 4.5:1),
 * which axe cannot measure without a layout engine.
 *
 * axe reads the rendered DOM: names of buttons, inputs and regions, ARIA
 * roles and states, lists, ids. Keyboard use is checked here too: every
 * control is a real button, link or input, so it takes the focus.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SetupPage from "@/app/control-plane/setup/page";
import { LoginForm } from "@/components/control-plane/AuthGate";
import TrashCard from "@/components/control-plane/TrashCard";
import Nucleo from "@/components/nucleo/Nucleo";
import type { SettingField, SettingsView } from "@/lib/api/settings";
import { chooseLanguage, type Lang } from "@/lib/i18n";

import { installEventSource, stubFetch } from "./helpers";

vi.mock("next/link", () => ({
    default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
        <a href={href} {...rest}>
            {children}
        </a>
    ),
}));

/** The violations axe finds, as "rule: what" lines (empty when there are none). */
async function violations(root: Element): Promise<string[]> {
    const result = await axe.run(root, {
        rules: {
            // Needs a layout engine: the palette is checked below instead.
            "color-contrast": { enabled: false },
            // A component alone is not a whole page with its landmarks.
            region: { enabled: false },
        },
    });
    return result.violations.map(
        (item) =>
            `${item.id}: ${item.help} (${item.nodes.map((node) => node.target.join(" ")).join(", ")})`
    );
}

function setting(name: string, value: string, extra: Partial<SettingField> = {}): SettingField {
    return {
        name,
        group: "models",
        label: name,
        kind: "text",
        help: "",
        default: "",
        value,
        source: "default",
        ...extra,
    };
}

function settingsView(): SettingsView {
    const chain = { chain: ["openai:gpt-5.5"], custom: false };
    return {
        settings: [
            setting("OPENAI_MODEL", "gpt-5.5"),
            setting("AEHUB_CHECKER_MODEL", "gpt-5.5-mini"),
            setting("AEHUB_MODEL_ROLES", "", { kind: "roles" }),
            setting("AEHUB_AGENT_FOLDERS", "", { group: "tools" }),
            setting("AEHUB_VOICE", "local", {
                kind: "choice",
                group: "voice",
                options: ["local", "off"],
            }),
        ],
        secrets: [
            {
                name: "OPENAI_API_KEY",
                label: "OpenAI API key",
                used_for: "openai",
                configured: true,
            },
        ],
        issues: [],
        models: [{ model: "gpt-5.5", providers: ["openai"], roles: ["architect"], priced: false }],
        roles: {
            architect: chain,
            research: chain,
            critic: { ...chain, chain: ["openai:gpt-5.5-mini"] },
            fast_worker: chain,
            triage: chain,
        },
        providers: {
            openai: { key: true, needs_key: true },
            local: { key: false, needs_key: false, base_url: "http://localhost:11434/v1" },
        },
        workspace: { path: "/app/workspace", exists: true },
        ready: true,
        onboarding: { completed: false, completed_at: null },
    } as SettingsView;
}

const NUCLEO_ROUTES = {
    "GET /api/approvals": () => ({ status: 200, body: [] }),
    "GET /api/runs/stats": () => ({
        status: 200,
        body: { budget: { month_spent: 0.4, monthly_budget: 30 } },
    }),
    "GET /api/runs/live": () => ({
        status: 200,
        body: { halted: false, halt_reason: null, limits: {}, runs: [] },
    }),
    "GET /api/conversations": () => ({
        status: 200,
        body: {
            total: 1,
            conversations: [
                {
                    id: "trip",
                    title: "Organizza il viaggio",
                    turns: 2,
                    started_at: null,
                    updated_at: "2026-11-27T10:00:00",
                    match: null,
                },
            ],
        },
    }),
};

describe.each<Lang>(["it", "en"])("accessibility (%s)", (lang) => {
    beforeEach(() => chooseLanguage(lang));

    it("the Nucleo, with its conversation and its history", async () => {
        installEventSource();
        stubFetch(NUCLEO_ROUTES);
        const { container } = render(<Nucleo />);
        expect(await violations(container)).toEqual([]);

        fireEvent.click(
            screen.getByRole("button", { name: lang === "it" ? /CRONOLOGIA/ : /HISTORY/ })
        );
        await screen.findByText("Organizza il viaggio");
        expect(await violations(container)).toEqual([]);
    });

    it("each step of the first start", async () => {
        stubFetch({ "GET /api/settings": () => ({ status: 200, body: settingsView() }) });
        const { container } = render(<SetupPage />);
        const steps = await screen.findAllByRole("button", { name: /^\d\. / });
        expect(steps).toHaveLength(3);
        for (const step of steps) {
            fireEvent.click(step);
            expect(await violations(container)).toEqual([]);
        }
    });

    it("the trash with an item, and the login", async () => {
        stubFetch({
            "GET /api/tools/trash": () => ({
                status: 200,
                body: {
                    days: 30,
                    items: [
                        {
                            id: "1",
                            original: "/w/a.txt",
                            deleted_at: "2026-11-27T10:00:00",
                            kind: "file",
                            size: 10,
                        },
                    ],
                },
            }),
        });
        const { container } = render(
            <>
                <TrashCard />
                <LoginForm onSignedIn={() => undefined} />
            </>
        );
        await screen.findByText("/w/a.txt");
        expect(await violations(container)).toEqual([]);
    });
});

describe("contrast of the palette (WCAG AA)", () => {
    const css = readFileSync(resolve(__dirname, "../src/app/style/globals.css"), "utf8");
    const token = (name: string) => {
        const found = new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`).exec(css);
        if (!found) throw new Error(`--${name} is not a hex color in globals.css`);
        return found[1];
    };
    const luminance = (hex: string) => {
        const [r, g, b] = [1, 3, 5].map((at) => {
            const c = parseInt(hex.slice(at, at + 2), 16) / 255;
            return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const ratio = (a: string, b: string) => {
        const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
        return (light + 0.05) / (dark + 0.05);
    };

    it.each(["ink", "dim", "hint", "ice", "amber", "danger", "ok"])(
        "--%s is readable on every background",
        (name) => {
            for (const background of ["void", "deep"]) {
                expect(
                    ratio(token(name), token(background)),
                    `--${name} on --${background}`
                ).toBeGreaterThanOrEqual(4.5);
            }
            expect(ratio(token(name), "#0c1734"), `--${name} on the cards`).toBeGreaterThanOrEqual(
                4.5
            );
        }
    );

    it("no text is written in --faint, the color of lines", () => {
        const sources = [
            "../src/app/style/globals.css",
            "../src/components/nucleo/nucleo.module.css",
            "../src/components/control-plane/control.module.css",
        ].map((path) => readFileSync(resolve(__dirname, path), "utf8"));
        for (const source of sources) {
            expect(source).not.toMatch(/(^|[\s;{])color:\s*var\(--faint\)/m);
        }
    });
});
