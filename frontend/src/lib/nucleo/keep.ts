/**
 * @file frontend/src/lib/nucleo/keep.ts
 * @description What the Nucleo shows, kept while you visit the other pages
 * of this tab: the conversation, the events, the runs and the commands
 * still running.
 *
 * Without it, going to a run's details and back emptied the conversation,
 * the runs and the events until the next run. It lives in memory only
 * (this tab, until it is reloaded), like the page itself.
 *
 * Commands are kept by the id the page gives each one, sent with it and
 * carried by its drafts and its end (answer.delta, answer.final): several
 * can run together, and the answer of one that ends while you are on
 * another page is waiting in the conversation when you come back.
 */

import type { NucleoState } from "./engine";
import type { RunsState } from "./runs";

export interface ChatLine {
    id: number;
    who: "me" | "aehub" | "system";
    text: string;
    channel?: "voice" | "text";
    // "instant · 8 ms" when the reply came without the model (ADR-035).
    note?: string;
}

export interface NucleoSnapshot {
    nucleo: NucleoState;
    chat: ChatLine[];
    runs: RunsState;
    /** The tab on the right (events or runs): back from a run's details, on runs. */
    tab: "events" | "runs";
}

export interface LiveCommand {
    /**
     * Its request no longer brings the answer: a proxy cut it (502/504), or
     * the page that sent it was left. The end comes as an event instead.
     */
    adrift: boolean;
}

let snapshot: NucleoSnapshot | null = null;

/** The commands sent and not answered yet, by id. */
export const liveCommands = new Map<string, LiveCommand>();

export function recallNucleo(): NucleoSnapshot | null {
    return snapshot;
}

export function keepNucleo(next: NucleoSnapshot): void {
    snapshot = next;
}

/** A line that came while the Nucleo was not on screen: it is there on return. */
export function keepLine(line: Omit<ChatLine, "id">): void {
    if (!snapshot) {
        return;
    }
    const id = snapshot.chat.reduce((top, entry) => Math.max(top, entry.id), 0) + 1;
    snapshot = { ...snapshot, chat: [...snapshot.chat, { ...line, id }] };
}

/** A new command's id (letters, digits and dashes, as the backend accepts). */
export function newCommandId(): string {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
        return crypto.randomUUID();
    }
    return `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Start again from nothing (the tests, between cases). */
export function forgetNucleo(): void {
    snapshot = null;
    liveCommands.clear();
}
