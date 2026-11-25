/**
 * @file frontend/src/lib/nucleo/home.ts
 * @description Italian text of the CASA page (F7): device types, states and
 * the backend's errors.
 */

import type { DeviceFormat, DeviceState, DeviceType, KnownState } from "@/lib/api/home";

export const TYPE_LABEL: Record<DeviceType, string> = {
    light: "Luce",
    lock: "Serratura",
};

export const FORMAT_LABEL: Record<DeviceFormat, string> = {
    zigbee2mqtt: "Zigbee2MQTT",
    tasmota: "Tasmota",
};

const STATE_LABEL: Record<DeviceState, string> = {
    on: "accesa",
    off: "spenta",
    locked: "chiusa a chiave",
    unlocked: "aperta",
};

export function stateTone(state: DeviceState | null): "ok" | "warn" | undefined {
    if (state === "on" || state === "locked") {
        return "ok";
    }
    return state === "unlocked" ? "warn" : undefined;
}

export function stateLabel(known: KnownState): string {
    if (!known.state) {
        return "stato sconosciuto";
    }
    const level = known.brightness !== undefined && known.state === "on" ? ` al ${known.brightness}%` : "";
    return `${STATE_LABEL[known.state]}${level}`;
}

function clock(at: string): string {
    return new Date(at).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

/** Where a state comes from: a command sent is not proof the device obeyed. */
export function stateSource(known: KnownState): string {
    if (!known.at) {
        return "Nessun comando da quando ÆHub è partito.";
    }
    if (known.read) {
        return known.state
            ? `Detto dal dispositivo alle ${clock(known.at)}.`
            : `Il dispositivo ha risposto alle ${clock(known.at)}, ma la risposta non si capisce.`;
    }
    const who = known.by === "agent" ? "dall'agente" : "da qui";
    return `Ultimo comando alle ${clock(known.at)}, ${who}: il dispositivo non l'ha confermato.`;
}

const ERRORS: [RegExp, string][] = [
    [/^The device did not answer/, "Il dispositivo non ha risposto."],
    [/^No MQTT broker/, "Manca l'indirizzo del broker MQTT."],
    [/must look like mqtt/, "L'indirizzo del broker deve essere come mqtt://host:1883 o mqtts://host:8883."],
    [/^Broker unreachable/, "Il broker non si raggiunge: controlla indirizzo e porta."],
    [/^The broker refused/, "Il broker ha rifiutato il collegamento: controlla utente e password."],
    [/^The broker did not answer/, "Il broker non ha risposto in tempo."],
    [/has no known shape/, "Il topic non ha una forma nota: ÆHub non sa come chiedere lo stato a questo dispositivo."],
    [/^Already in the device file/, "Questo id è già nel file dei dispositivi."],
    [/^Unauthorized/, "Lo strumento è spento o non è permesso: controlla STRUMENTI."],
    [/needs your confirmation/, "Questa azione va confermata."],
    [/^Unknown device/, "Dispositivo non trovato."],
    [/^The home tools are not available/, "Gli strumenti della casa non sono disponibili."],
];

export function homeError(message: string): string {
    for (const [pattern, text] of ERRORS) {
        if (pattern.test(message)) {
            return text;
        }
    }
    return message;
}
