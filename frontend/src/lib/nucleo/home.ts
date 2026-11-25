/**
 * @file frontend/src/lib/nucleo/home.ts
 * @description Text of the Home page (F7) in each interface language: device
 * types, states and the backend's errors.
 */

import type { DeviceFormat, DeviceState, DeviceType, KnownState } from "@/lib/api/home";
import { catalog, localeOf, type Lang } from "@/lib/i18n";

export const TYPE_LABEL = catalog<Record<DeviceType, string>>({
    en: { light: "Light", lock: "Lock" },
    it: { light: "Luce", lock: "Serratura" },
});

export const FORMAT_LABEL: Record<DeviceFormat, string> = {
    zigbee2mqtt: "Zigbee2MQTT",
    tasmota: "Tasmota",
};

const TEXT = catalog({
    en: {
        states: { on: "on", off: "off", locked: "locked", unlocked: "unlocked" } as Record<DeviceState, string>,
        unknown: "state unknown",
        level: (brightness: number) => ` at ${brightness}%`,
        noCommand: "No command since ÆHub started.",
        told: (time: string) => `Reported by the device at ${time}.`,
        unclear: (time: string) => `The device answered at ${time}, but the answer is not clear.`,
        byAgent: "by the agent",
        byHere: "from here",
        lastCommand: (time: string, who: string) => `Last command at ${time}, ${who}: the device did not confirm it.`,
    },
    it: {
        states: { on: "accesa", off: "spenta", locked: "chiusa a chiave", unlocked: "aperta" } as Record<
            DeviceState,
            string
        >,
        unknown: "stato sconosciuto",
        level: (brightness: number) => ` al ${brightness}%`,
        noCommand: "Nessun comando da quando ÆHub è partito.",
        told: (time: string) => `Detto dal dispositivo alle ${time}.`,
        unclear: (time: string) => `Il dispositivo ha risposto alle ${time}, ma la risposta non si capisce.`,
        byAgent: "dall'agente",
        byHere: "da qui",
        lastCommand: (time: string, who: string) =>
            `Ultimo comando alle ${time}, ${who}: il dispositivo non l'ha confermato.`,
    },
});

export function stateTone(state: DeviceState | null): "ok" | "warn" | undefined {
    if (state === "on" || state === "locked") {
        return "ok";
    }
    return state === "unlocked" ? "warn" : undefined;
}

export function stateLabel(known: KnownState, lang: Lang = "en"): string {
    const t = TEXT[lang];
    if (!known.state) {
        return t.unknown;
    }
    const level = known.brightness !== undefined && known.state === "on" ? t.level(known.brightness) : "";
    return `${t.states[known.state]}${level}`;
}

function clock(at: string, lang: Lang): string {
    return new Date(at).toLocaleTimeString(localeOf(lang), { hour: "2-digit", minute: "2-digit" });
}

/** Where a state comes from: a command sent is not proof the device obeyed. */
export function stateSource(known: KnownState, lang: Lang = "en"): string {
    const t = TEXT[lang];
    if (!known.at) {
        return t.noCommand;
    }
    if (known.read) {
        return known.state ? t.told(clock(known.at, lang)) : t.unclear(clock(known.at, lang));
    }
    return t.lastCommand(clock(known.at, lang), known.by === "agent" ? t.byAgent : t.byHere);
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

/** A home error in the interface language; English is the backend's own text. */
export function homeError(message: string, lang: Lang = "en"): string {
    if (lang === "en") {
        return message;
    }
    for (const [pattern, text] of ERRORS) {
        if (pattern.test(message)) {
            return text;
        }
    }
    return message;
}
