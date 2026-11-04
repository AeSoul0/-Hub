import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";

import HomePage from "@/app/control-plane/home/page";
import {
    deviceId,
    knownState,
    ownDevices,
    topicHint,
    withDevice,
    withoutDevice,
    type HomeDevice,
    type HomeView,
} from "@/lib/api/home";
import { homeError, stateLabel, stateSource } from "@/lib/nucleo/home";

import { stubFetch } from "./helpers";

const LIGHT: HomeDevice = {
    id: "living_light",
    name: "Luce del soggiorno",
    type: "light",
    topic: "z2m/living_light/set",
    format: "zigbee2mqtt",
    source: "app",
};

const DOOR: HomeDevice = {
    id: "front_door",
    name: "Porta d'ingresso",
    type: "lock",
    topic: "z2m/front_door/set",
    format: "zigbee2mqtt",
    source: "file",
};

function view(extra: Partial<HomeView> = {}): HomeView {
    const tool = { registered: true, disabled: false };
    return {
        devices: [LIGHT, DOOR],
        errors: {},
        file: "C:/config/home.json",
        broker: { url: "mqtt://broker.lan:1883", username: "", password_set: false, error: null },
        tools: { home_list_devices: tool, home_set_light: tool, home_lock: tool, home_unlock: tool },
        desktop: false,
        limits: { max_devices: 200, types: ["light", "lock"], formats: ["zigbee2mqtt", "tasmota"] },
        ...extra,
    };
}

function settingsBody(url = "mqtt://broker.lan:1883") {
    const field = (name: string, value: string) => ({
        name,
        group: "home",
        label: name,
        kind: "text",
        help: "",
        default: "",
        value,
        source: "database",
        options: [],
    });
    return {
        settings: [field("AEHUB_MQTT_URL", url), field("AEHUB_MQTT_USERNAME", "")],
        secrets: [],
        issues: [],
        ready: true,
        onboarding: { completed: true, completed_at: null },
    };
}

function routes(home: HomeView, extra: Parameters<typeof stubFetch>[0] = {}) {
    return stubFetch({
        "GET /api/home": () => ({ status: 200, body: home }),
        "GET /api/settings": () => ({ status: 200, body: settingsBody() }),
        ...extra,
    });
}

function bodyOf(fetchMock: ReturnType<typeof stubFetch>, path: string): unknown {
    const call = [...fetchMock.mock.calls].reverse().find(([input]) => new URL(String(input)).pathname === path);
    return call ? JSON.parse(String(call[1]?.body)) : undefined;
}

describe("the plain logic of the home", () => {
    it("builds ids and topics", () => {
        expect(deviceId("Luce del Soggiorno")).toBe("luce_del_soggiorno");
        expect(deviceId("  Città è più! ")).toBe("citta_e_piu");
        expect(topicHint("zigbee2mqtt", "a")).toBe("zigbee2mqtt/a/set");
        expect(topicHint("tasmota", "a")).toBe("cmnd/a/POWER");
    });

    it("sends back only the devices declared here", () => {
        const own = ownDevices([LIGHT, DOOR]);
        expect(own.map((device) => device.id)).toEqual(["living_light"]);
        expect(own[0]).not.toHaveProperty("source");

        const edited = withDevice(own, { ...own[0], name: "Nuova" });
        expect(edited).toHaveLength(1);
        expect(edited[0].name).toBe("Nuova");
        expect(withDevice(own, { ...own[0], id: "other" })).toHaveLength(2);
        expect(withoutDevice(own, "living_light")).toEqual([]);
    });

    it("never presents a command as what the device said", () => {
        const command = { state: "on" as const, at: "2026-10-30T10:00:00+00:00", by: "agent" };
        const sent = knownState({ ...LIGHT, command });
        expect(sent.read).toBe(false);
        expect(stateSource(sent)).toContain("non l'ha confermato");
        expect(stateSource(sent)).toContain("dall'agente");

        const older = { state: "off" as const, at: "2026-10-30T09:00:00+00:00" };
        expect(knownState({ ...LIGHT, command, reading: older }).state).toBe("on");

        const newer = { state: "off" as const, at: "2026-10-30T11:00:00+00:00" };
        const read = knownState({ ...LIGHT, command, reading: newer });
        expect(read.state).toBe("off");
        expect(stateSource(read)).toContain("Detto dal dispositivo");

        expect(stateLabel(knownState(LIGHT))).toBe("stato sconosciuto");
        expect(stateLabel({ state: "on", brightness: 40, at: null, read: false })).toBe("accesa al 40%");
    });

    it("translates the backend's errors and keeps the others", () => {
        expect(homeError("The device did not answer.")).toBe("Il dispositivo non ha risposto.");
        expect(homeError("device 'x': declared twice.")).toBe("device 'x': declared twice.");
    });
});

describe("CASA", () => {
    it("lists the devices with their origin", async () => {
        routes(view());
        render(<HomePage />);

        const light = await screen.findByRole("listitem", { name: "Luce del soggiorno" });
        expect(within(light).getByText(/aggiunto da qui/)).toBeTruthy();
        expect(within(light).getByText("stato sconosciuto")).toBeTruthy();

        const door = screen.getByRole("listitem", { name: "Porta d'ingresso" });
        expect(within(door).getByText(/dal file/)).toBeTruthy();
        // The file's devices are read only.
        expect(within(door).queryByRole("button", { name: /Modifica/ })).toBeNull();
        expect(screen.getByText("C:/config/home.json")).toBeTruthy();
    });

    it("sends a command and shows what came back", async () => {
        const answered = { ...LIGHT, command: { state: "on", at: "2026-10-30T10:00:00+00:00", by: "control-plane" } };
        const fetchMock = routes(view(), {
            "POST /api/home/devices/living_light/command": () => ({ status: 200, body: { device: answered } }),
        });
        render(<HomePage />);

        fireEvent.click(await screen.findByRole("button", { name: "Accendi Luce del soggiorno" }));

        await screen.findByText("accesa");
        expect(bodyOf(fetchMock, "/api/home/devices/living_light/command")).toEqual({ action: "on" });
    });

    it("sends the brightness only when it was chosen", async () => {
        const fetchMock = routes(view(), {
            "POST /api/home/devices/living_light/command": () => ({ status: 200, body: { device: LIGHT } }),
        });
        render(<HomePage />);

        const light = await screen.findByRole("listitem", { name: "Luce del soggiorno" });
        fireEvent.change(within(light).getByRole("slider"), { target: { value: "30" } });
        fireEvent.click(within(light).getByRole("button", { name: "Accendi Luce del soggiorno" }));

        await waitFor(() =>
            expect(bodyOf(fetchMock, "/api/home/devices/living_light/command")).toEqual({
                action: "on",
                brightness: 30,
            }),
        );
    });

    it("opens a door only after a second click, and says it stays on record", async () => {
        const fetchMock = routes(view(), {
            "POST /api/home/devices/front_door/command": () => ({ status: 200, body: { device: DOOR } }),
        });
        render(<HomePage />);

        fireEvent.click(await screen.findByRole("button", { name: "Apri Porta d'ingresso" }));

        expect(bodyOf(fetchMock, "/api/home/devices/front_door/command")).toBeUndefined();
        expect(screen.getByText(/resta nel registro come approvazione/)).toBeTruthy();

        fireEvent.click(screen.getByRole("button", { name: "Annulla" }));
        expect(bodyOf(fetchMock, "/api/home/devices/front_door/command")).toBeUndefined();

        fireEvent.click(screen.getByRole("button", { name: "Apri Porta d'ingresso" }));
        fireEvent.click(screen.getByRole("button", { name: "Conferma: apri" }));

        await waitFor(() =>
            expect(bodyOf(fetchMock, "/api/home/devices/front_door/command")).toEqual({
                action: "unlock",
                confirm: true,
            }),
        );
    });

    it("blocks what is turned off in STRUMENTI, and says so", async () => {
        const tool = { registered: true, disabled: false };
        routes(
            view({
                tools: {
                    home_list_devices: tool,
                    home_set_light: tool,
                    home_lock: tool,
                    home_unlock: { registered: true, disabled: true },
                },
            }),
        );
        render(<HomePage />);

        const open = (await screen.findByRole("button", { name: "Apri Porta d'ingresso" })) as HTMLButtonElement;
        expect(open.disabled).toBe(true);
        expect(screen.getByText(/Spento in STRUMENTI/)).toBeTruthy();
    });

    it("keeps commands off without a broker", async () => {
        routes(
            view({
                broker: { url: "", username: "", password_set: false, error: "No MQTT broker: set AEHUB_MQTT_URL." },
            }),
        );
        render(<HomePage />);

        const on = (await screen.findByRole("button", { name: "Accendi Luce del soggiorno" })) as HTMLButtonElement;
        expect(on.disabled).toBe(true);
        expect(screen.getByText("broker mancante")).toBeTruthy();
    });

    it("reports a device that does not answer, in Italian", async () => {
        routes(view(), {
            "POST /api/home/devices/living_light/state": () => ({
                status: 504,
                body: { detail: "The device did not answer." },
            }),
        });
        render(<HomePage />);

        fireEvent.click(await screen.findByRole("button", { name: "Leggi lo stato di Luce del soggiorno" }));

        expect(await screen.findByText(/Il dispositivo non ha risposto/)).toBeTruthy();
    });

    it("adds a device, keeping those already declared here and leaving the file's out", async () => {
        const fetchMock = routes(view(), {
            "PUT /api/home/devices": () => ({ status: 200, body: view() }),
        });
        render(<HomePage />);

        const form = await screen.findByRole("form", { name: "Dispositivo" });
        fireEvent.change(within(form).getByLabelText("Nome"), { target: { value: "Lampada Studio" } });
        fireEvent.change(within(form).getByLabelText("Formato"), { target: { value: "tasmota" } });
        fireEvent.change(within(form).getByLabelText("Topic dei comandi"), {
            target: { value: "cmnd/lampada/POWER" },
        });
        fireEvent.click(within(form).getByRole("button", { name: "Aggiungi" }));

        await waitFor(() =>
            expect(bodyOf(fetchMock, "/api/home/devices")).toEqual({
                devices: [
                    {
                        id: "living_light",
                        name: "Luce del soggiorno",
                        type: "light",
                        topic: "z2m/living_light/set",
                        format: "zigbee2mqtt",
                    },
                    {
                        id: "lampada_studio",
                        name: "Lampada Studio",
                        type: "light",
                        topic: "cmnd/lampada/POWER",
                        format: "tasmota",
                    },
                ],
            }),
        );
    });

    it("a lock has only one format", async () => {
        routes(view());
        render(<HomePage />);

        const form = await screen.findByRole("form", { name: "Dispositivo" });
        fireEvent.change(within(form).getByLabelText("Formato"), { target: { value: "tasmota" } });
        fireEvent.change(within(form).getByLabelText("Tipo"), { target: { value: "lock" } });

        const format = within(form).getByLabelText("Formato") as HTMLSelectElement;
        expect(format.value).toBe("zigbee2mqtt");
        expect(format.disabled).toBe(true);
    });

    it("shows why a list is refused", async () => {
        routes(view(), {
            "PUT /api/home/devices": () => ({ status: 422, body: { detail: "Already in the device file: a." } }),
        });
        render(<HomePage />);

        const form = await screen.findByRole("form", { name: "Dispositivo" });
        fireEvent.change(within(form).getByLabelText("Nome"), { target: { value: "A" } });
        fireEvent.change(within(form).getByLabelText("Topic dei comandi"), { target: { value: "x/set" } });
        fireEvent.click(within(form).getByRole("button", { name: "Aggiungi" }));

        expect(await screen.findByText("Questo id è già nel file dei dispositivi.")).toBeTruthy();
    });

    it("removes a device after a confirmation", async () => {
        const fetchMock = routes(view(), {
            "PUT /api/home/devices": () => ({ status: 200, body: view({ devices: [DOOR] }) }),
        });
        render(<HomePage />);

        fireEvent.click(await screen.findByRole("button", { name: "Togli Luce del soggiorno" }));
        expect(bodyOf(fetchMock, "/api/home/devices")).toBeUndefined();

        fireEvent.click(screen.getByRole("button", { name: "Conferma: togli" }));

        await waitFor(() => expect(bodyOf(fetchMock, "/api/home/devices")).toEqual({ devices: [] }));
    });

    it("checks the broker", async () => {
        routes(view(), {
            "POST /api/home/broker/check": () => ({ status: 200, body: { ok: false, error: "The broker refused the connection." } }),
        });
        render(<HomePage />);

        fireEvent.click(await screen.findByRole("button", { name: "Prova il collegamento" }));

        expect(await screen.findByText(/controlla utente e password/)).toBeTruthy();
    });

    it("asks for the password only where it can be saved, and never shows it", async () => {
        const fetchMock = routes(view({ desktop: true }), {
            "PUT /api/desktop/secrets": () => ({ status: 200, body: { saved: ["AEHUB_MQTT_PASSWORD"] } }),
        });
        render(<HomePage />);

        const field = (await screen.findByLabelText("Password del broker")) as HTMLInputElement;
        expect(field.type).toBe("password");

        fireEvent.change(field, { target: { value: "segreta" } });
        fireEvent.click(screen.getByRole("button", { name: "Salva la password" }));

        await screen.findByText("Password salvata nel portachiavi del sistema.");
        expect(bodyOf(fetchMock, "/api/desktop/secrets")).toEqual({ AEHUB_MQTT_PASSWORD: "segreta" });
        expect(field.value).toBe("");
    });

    it("points to the launcher outside the desktop app", async () => {
        routes(view());
        render(<HomePage />);

        await screen.findByText("python scripts/aehub.py setup");
        expect(screen.queryByLabelText("Password del broker")).toBeNull();
    });
});
