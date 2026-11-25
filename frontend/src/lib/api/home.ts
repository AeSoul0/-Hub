/**
 * @file frontend/src/lib/api/home.ts
 * @description Home devices (F7, ADR-028): the shape of GET /api/home and
 * the plain logic of the CASA page.
 *
 * The password of the broker never comes through here: the API only says
 * whether it is set.
 */

export type DeviceType = "light" | "lock";
export type DeviceFormat = "zigbee2mqtt" | "tasmota";
export type DeviceSource = "file" | "app";
export type DeviceState = "on" | "off" | "locked" | "unlocked";
export type HomeAction = "on" | "off" | "lock" | "unlock";

export interface DeviceCommand {
    state: DeviceState;
    brightness?: number;
    at: string;
    /** "control-plane" for a click here, "agent" for a run. */
    by: string;
}

export interface DeviceReading {
    /** null when the device answered something unreadable. */
    state: DeviceState | null;
    brightness?: number;
    at: string;
}

export interface HomeDevice {
    id: string;
    name: string;
    type: DeviceType;
    topic: string;
    format: DeviceFormat;
    source: DeviceSource;
    command?: DeviceCommand;
    reading?: DeviceReading;
}

export interface HomeToolStatus {
    registered: boolean;
    disabled: boolean;
}

export interface HomeView {
    devices: HomeDevice[];
    /** Problems by origin: "file", "app" or "all". */
    errors: Record<string, string>;
    file: string | null;
    broker: {
        url: string;
        username: string;
        password_set: boolean;
        error: string | null;
    };
    tools: Record<string, HomeToolStatus>;
    desktop: boolean;
    limits: { max_devices: number; types: DeviceType[]; formats: DeviceFormat[] };
}

/** What can be sent to PUT /api/home/devices. */
export interface DeviceEntry {
    id: string;
    name: string;
    type: DeviceType;
    topic: string;
    format: DeviceFormat;
}

export const ACTION_TOOL: Record<HomeAction, string> = {
    on: "home_set_light",
    off: "home_set_light",
    lock: "home_lock",
    unlock: "home_unlock",
};

/** The devices the page may change: those of the device file stay as they are. */
export function ownDevices(devices: HomeDevice[]): DeviceEntry[] {
    return devices
        .filter((device) => device.source === "app")
        .map(({ id, name, type, topic, format }) => ({ id, name, type, topic, format }));
}

/** Add `entry`, or replace the device with the same id, keeping the order. */
export function withDevice(entries: DeviceEntry[], entry: DeviceEntry): DeviceEntry[] {
    return entries.some((item) => item.id === entry.id)
        ? entries.map((item) => (item.id === entry.id ? entry : item))
        : [...entries, entry];
}

export function withoutDevice(entries: DeviceEntry[], id: string): DeviceEntry[] {
    return entries.filter((item) => item.id !== id);
}

/** A device id from its name: "Luce del soggiorno" becomes "luce_del_soggiorno". */
export function deviceId(name: string): string {
    return name
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .slice(0, 64);
}

/** The usual command topic of a device, as a starting point. */
export function topicHint(format: DeviceFormat, id: string): string {
    const name = id || "nome";
    return format === "tasmota" ? `cmnd/${name}/POWER` : `zigbee2mqtt/${name}/set`;
}

export interface KnownState {
    state: DeviceState | null;
    brightness?: number;
    at: string | null;
    /** True for what the device said, false for the last command sent. */
    read: boolean;
    by?: string;
}

/** The newest thing known about a device: a reading wins over an older command. */
export function knownState(device: HomeDevice): KnownState {
    const { command, reading } = device;

    if (reading && (!command || reading.at >= command.at)) {
        return { state: reading.state, brightness: reading.brightness, at: reading.at, read: true };
    }
    if (command) {
        return { state: command.state, brightness: command.brightness, at: command.at, read: false, by: command.by };
    }
    return { state: null, at: null, read: false };
}
