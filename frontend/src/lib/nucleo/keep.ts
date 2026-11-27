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
 *
 * The conversation the next command goes on in (N6) is also kept in the
 * browser (localStorage), so a reload goes on in the same one: an id the
 * page makes, sent with each command; "_" stands for the principal's own
 * session, the id "". Only its id is kept, never what was said.
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
    /** The tab on the left: the conversation, or the past conversations (N6). */
    leftTab?: "chat" | "history";
}

export interface LiveCommand {
    /**
     * Its request no longer brings the answer: a proxy cut it (502/504), or
     * the page that sent it was left. The end comes as an event instead.
     */
    adrift: boolean;
}

let snapshot: NucleoSnapshot | null = null;

const CONVERSATION_KEY = "aehub.nucleo.conversation";
const OWN_SESSION = "_";
const CONVERSATION_ID = /^[A-Za-z0-9-]{1,64}$/;
let conversation: string | null = null;

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

/**
 * The conversation the next command goes on in: the one kept in this
 * browser, else a new one ("" is the principal's own session).
 */
export function currentConversation(): string {
    if (conversation !== null) {
        return conversation;
    }
    let stored = "";
    try {
        stored = window.localStorage.getItem(CONVERSATION_KEY) ?? "";
    } catch {
        // No storage (a private window): a new conversation at each load.
    }
    conversation =
        stored === OWN_SESSION ? "" : CONVERSATION_ID.test(stored) ? stored : newCommandId();
    return conversation;
}

/** Go on in this conversation from now on, here and after a reload. */
export function rememberConversation(id: string): void {
    conversation = id;
    try {
        window.localStorage.setItem(CONVERSATION_KEY, id || OWN_SESSION);
    } catch {
        // Kept for this tab only.
    }
}

/** Start again from nothing (the tests, between cases). */
export function forgetNucleo(): void {
    snapshot = null;
    conversation = null;
    liveCommands.clear();
}
