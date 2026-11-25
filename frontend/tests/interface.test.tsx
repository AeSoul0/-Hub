/**
 * @file frontend/tests/interface.test.tsx
 * @description The interface language and the voice language notice
 * (ADR-034): English by default, the choice in Settings, the language the
 * backend gives (also when Aurora changes it), and the notice when the
 * chosen voice speaks another language.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import SettingsPage from "@/app/control-plane/settings/page";
import ToolsPage from "@/app/control-plane/tools/page";
import VoicePage from "@/app/control-plane/voice/page";
import InterfaceProvider, { noticePair } from "@/components/interface/InterfaceProvider";
import Nucleo from "@/components/nucleo/Nucleo";
import type { SettingField, SettingsView } from "@/lib/api/settings";
import { applyInterface, chooseLanguage, useLanguage, type InterfaceState } from "@/lib/i18n";
import { piperLanguage, previewText } from "@/lib/nucleo/voice";

import { FakeEventSource, installEventSource, stubFetch } from "./helpers";

vi.mock("next/link", () => ({
    default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
        <a href={href} {...rest}>
            {children}
        </a>
    ),
}));

function setting(name: string, value: string, group: SettingField["group"] = "interface"): SettingField {
    return {
        name,
        group,
        label: name,
        kind: "choice",
        help: "",
        default: value,
        value,
        source: "default",
        options: [],
    };
}

function settingsView(values: Record<string, string> = {}): SettingsView {
    return {
        settings: [
            setting("AEHUB_UI_LANGUAGE", values.AEHUB_UI_LANGUAGE ?? "en"),
            setting("AEHUB_VOICE_LANGUAGE_WARNING", values.AEHUB_VOICE_LANGUAGE_WARNING ?? "on"),
        ],
        secrets: [],
        issues: [],
        models: [],
        roles: {
            architect: { chain: ["openai:gpt-5.5"], custom: false },
            research: { chain: ["openai:gpt-5.5"], custom: false },
            critic: { chain: ["openai:critic"], custom: false },
            fast_worker: { chain: ["openai:gpt-5.5"], custom: false },
            triage: { chain: ["openai:gpt-5.5"], custom: false },
        },
        providers: {
            openai: { key: true, needs_key: true },
            openrouter: { key: false, needs_key: true },
            local: { key: false, needs_key: false },
        },
        workspace: { path: "/w", exists: true },
        ready: true,
        onboarding: { completed: true, completed_at: "2026-11-25T10:00:00Z" },
    } as SettingsView;
}

function state(overrides: Partial<InterfaceState> = {}, voice: Partial<InterfaceState["voice"]> = {}): InterfaceState {
    return {
        language: "en",
        voice_language_warning: true,
        ...overrides,
        voice: { enabled: true, engine: "piper", name: "it_IT-paola-medium", language: "it", ...voice },
    };
}

const MODEL_LISTS = Object.fromEntries(
    ["openai", "openrouter", "local"].map((provider) => [
        `GET /api/settings/provider-models/${provider}`,
        () => ({ status: 200, body: { provider, models: [] } }),
    ]),
);

function putBodies(fetchMock: ReturnType<typeof stubFetch>, path: string): unknown[] {
    return fetchMock.mock.calls
        .filter(([input, init]) => String(input).includes(path) && init?.method === "PUT")
        .map(([, init]) => JSON.parse(String(init?.body)));
}

function Probe() {
    return <span data-testid="lang">{useLanguage()}</span>;
}

describe("the interface language", () => {
    it("is English by default", async () => {
        stubFetch({
            "GET /api/tools": () => ({ status: 500, body: { detail: "down" } }),
        });

        render(<ToolsPage />);

        expect(await screen.findByText(/Tools not available/)).toBeInTheDocument();
    });

    it("switches every page at once from Settings, and saves the choice for Aurora", async () => {
        let current = settingsView();
        const fetchMock = stubFetch({
            ...MODEL_LISTS,
            "GET /api/desktop": () => ({ status: 200, body: { desktop: false } }),
            "GET /api/settings": () => ({ status: 200, body: current }),
            "PUT /api/settings": () => {
                current = settingsView({ AEHUB_UI_LANGUAGE: "it" });
                return { status: 200, body: current };
            },
        });

        render(
            <>
                <SettingsPage />
                <Probe />
            </>,
        );

        expect(await screen.findByText("SETTINGS")).toBeInTheDocument();
        expect(screen.getByRole("radio", { name: "English" })).toBeChecked();

        fireEvent.click(screen.getByRole("radio", { name: "Italiano" }));

        expect(await screen.findByText("IMPOSTAZIONI")).toBeInTheDocument();
        expect(screen.getByTestId("lang")).toHaveTextContent("it");
        expect(document.documentElement.lang).toBe("it");
        await waitFor(() => expect(putBodies(fetchMock, "/api/settings")).toEqual([{ values: { AEHUB_UI_LANGUAGE: "it" } }]));
        expect(await screen.findByText("L'interfaccia è in italiano.")).toBeInTheDocument();
    });

    it("turns the voice notice back on from Settings", async () => {
        const fetchMock = stubFetch({
            ...MODEL_LISTS,
            "GET /api/desktop": () => ({ status: 200, body: { desktop: false } }),
            "GET /api/settings": () => ({ status: 200, body: settingsView({ AEHUB_VOICE_LANGUAGE_WARNING: "off" }) }),
            "PUT /api/settings": () => ({ status: 200, body: settingsView() }),
        });

        render(<SettingsPage />);

        const notice = await screen.findByRole("checkbox", {
            name: "Warn me when the chosen voice speaks another language than the interface",
        });
        expect(notice).not.toBeChecked();
        fireEvent.click(notice);

        await waitFor(() =>
            expect(putBodies(fetchMock, "/api/settings")).toEqual([{ values: { AEHUB_VOICE_LANGUAGE_WARNING: "on" } }]),
        );
    });

    it("comes from the backend, and follows Aurora when she changes it", async () => {
        installEventSource();
        stubFetch({ "GET /api/interface": () => ({ status: 200, body: state({ language: "it" }, { language: "it" }) }) });

        render(
            <>
                <InterfaceProvider />
                <Probe />
            </>,
        );

        await waitFor(() => expect(screen.getByTestId("lang")).toHaveTextContent("it"));
        expect(window.localStorage.getItem("aehub.language")).toBe("it");

        // Aurora ran set_interface_language("en"): the event switches the page.
        const stream = FakeEventSource.instances.find((source) => source.url.includes("scope=workspace"));
        const changed = state({ language: "en" }, { language: "en", name: "en_GB-alba-medium" });
        act(() => stream?.emit("interface.changed", changed as unknown as Record<string, unknown>));

        expect(screen.getByTestId("lang")).toHaveTextContent("en");
    });

    it("paints the first screen in the language remembered by this browser", () => {
        window.localStorage.setItem("aehub.language", "it");
        render(<Probe />);
        expect(screen.getByTestId("lang")).toHaveTextContent("it");
    });
});

describe("the voice language notice", () => {
    it("is due only when an enabled voice speaks another known language", () => {
        expect(noticePair(state())).toBe("en:it");
        expect(noticePair(state({ language: "it" }))).toBeNull();
        expect(noticePair(state({ voice_language_warning: false }))).toBeNull();
        expect(noticePair(state({}, { enabled: false }))).toBeNull();
        expect(noticePair(state({}, { language: null }))).toBeNull();
        expect(noticePair(null)).toBeNull();
    });

    it("says what differs, closes with OK and comes back on the next visit", async () => {
        installEventSource();
        stubFetch({ "GET /api/interface": () => ({ status: 200, body: state() }) });

        const first = render(<InterfaceProvider />);

        const dialog = await screen.findByRole("dialog", { name: "The voice speaks another language" });
        expect(dialog).toHaveTextContent(
            "The interface is in English, but the chosen voice (it_IT-paola-medium) speaks Italian",
        );
        expect(dialog).toHaveTextContent("Settings → Language, or by asking Aurora");

        fireEvent.click(screen.getByRole("button", { name: "OK" }));
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

        // Same browser session: it stays closed.
        first.unmount();
        render(<InterfaceProvider />);
        await act(async () => undefined);
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("turns itself off with Don't show this again", async () => {
        installEventSource();
        const fetchMock = stubFetch({
            "GET /api/interface": () => ({ status: 200, body: state() }),
            "PUT /api/settings": () => ({ status: 200, body: {} }),
        });

        render(<InterfaceProvider />);

        await screen.findByRole("dialog");
        fireEvent.click(screen.getByRole("checkbox", { name: "Don't show this again" }));
        fireEvent.click(screen.getByRole("button", { name: "OK" }));

        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
        expect(putBodies(fetchMock, "/api/settings")).toEqual([{ values: { AEHUB_VOICE_LANGUAGE_WARNING: "off" } }]);
    });

    it("speaks the interface language", async () => {
        installEventSource();
        stubFetch({ "GET /api/interface": () => ({ status: 200, body: state({ language: "it" }, { language: "en", name: "en_US-lessac-medium" }) }) });

        render(<InterfaceProvider />);

        const dialog = await screen.findByRole("dialog", { name: "La voce parla un'altra lingua" });
        expect(dialog).toHaveTextContent("L'interfaccia è in italiano, ma la voce scelta (en_US-lessac-medium) parla inglese");
        expect(screen.getByRole("checkbox", { name: "Non mostrare più" })).toBeInTheDocument();
    });
});

describe("the voice keeps its own language", () => {
    it("reads it from the Piper voice and picks a sample sentence in it", () => {
        expect(piperLanguage("it_IT-paola-medium")).toBe("it");
        expect(piperLanguage("en_GB-alba-medium")).toBe("en");
        expect(piperLanguage("???")).toBeNull();
        expect(previewText("en", "it")).toBe("Hi, I am ÆHub. This is my voice.");
        expect(previewText("it", "en")).toBe("Ciao, sono ÆHub. Questa è la mia voce.");
        expect(previewText(null, "en")).toBe("Hi, I am ÆHub. This is my voice.");
    });

    it("shows on the Voice page whatever the interface language", async () => {
        applyInterface(state());
        stubFetch({
            "GET /api/settings": () => ({
                status: 200,
                body: {
                    ...settingsView(),
                    settings: [
                        setting("AEHUB_STT_MODEL", "base", "voice"),
                        setting("AEHUB_STT_LANGUAGE", "it", "voice"),
                        setting("AEHUB_TTS_ENGINE", "piper", "voice"),
                        setting("AEHUB_TTS_VOICE", "it_IT-paola-medium", "voice"),
                        setting("AEHUB_ELEVENLABS_VOICE", "", "voice"),
                        setting("AEHUB_ELEVENLABS_MODEL", "eleven_flash_v2_5", "voice"),
                    ],
                },
            }),
            "GET /api/voice": () => ({
                status: 200,
                body: {
                    enabled: true,
                    missing: [],
                    stt: { model: "base", language: "it" },
                    tts: {
                        engine: "piper",
                        piper_voice: "it_IT-paola-medium",
                        elevenlabs_voice: "",
                        elevenlabs_key: false,
                        max_cloud_chars: 2500,
                    },
                    downloaded: { whisper: [], piper: [] },
                },
            }),
            "GET /api/desktop": () => ({ status: 200, body: { desktop: false } }),
        });

        render(<VoicePage />);

        expect(await screen.findByText("This voice speaks Italian: replies are read in Italian.")).toBeInTheDocument();
        expect(screen.getByRole("textbox", { name: "Sentence" })).toHaveValue("Ciao, sono ÆHub. Questa è la mia voce.");
    });
});

describe("the Nucleo in English", () => {
    it("labels its controls in English", async () => {
        installEventSource();
        chooseLanguage("en");
        stubFetch({
            "GET /api/approvals": () => ({ status: 200, body: [] }),
            "GET /api/runs/stats": () => ({ status: 200, body: { budget: { month_spent: 0, monthly_budget: 30 } } }),
            "GET /api/runs/live": () => ({ status: 200, body: { halted: false, runs: [], limits: null } }),
        });

        render(<Nucleo />);

        expect(screen.getByRole("textbox", { name: "Command" })).toHaveAttribute("placeholder", "Type a command…");
        expect(screen.getByRole("button", { name: "SEND" })).toBeInTheDocument();
        expect(screen.getByText("WAITING")).toBeInTheDocument();
    });
});
