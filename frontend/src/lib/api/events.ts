/**
 * @file frontend/src/lib/api/events.ts
 * @description Live Control Plane events over Server-Sent Events (M11).
 *
 * GET /api/events?scope=workspace streams the run states and approval events
 * of every session of the caller's workspace. Pages re-read their data when a
 * relevant event arrives instead of polling. EventSource reconnects by
 * itself; on every (re)connection the pages refresh once, so nothing missed
 * while offline stays hidden.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE_URL } from "@/lib/api/client";

export type ControlEventType =
    | "run.state"
    | "approval.requested"
    | "approval.decided"
    | "run.resumed"
    // Every run event, pushed live for the Nucleo (F1).
    | "engine.event";

export interface ControlEvent {
    type: string;
    data: Record<string, unknown>;
}

export type ConnectionState = "connecting" | "live" | "offline";

/**
 * Parse one SSE data line; returns null for anything that is not a
 * `{"type": ..., "data": ...}` event.
 */
export function parseEvent(raw: string): ControlEvent | null {
    try {
        const parsed = JSON.parse(raw);

        if (!parsed || typeof parsed.type !== "string") {
            return null;
        }

        const data =
            parsed.data && typeof parsed.data === "object" && !Array.isArray(parsed.data)
                ? (parsed.data as Record<string, unknown>)
                : {};

        return { type: parsed.type, data };
    } catch {
        return null;
    }
}

export function workspaceEventsUrl(): string {
    return new URL("/api/events?scope=workspace", API_BASE_URL).toString();
}

/**
 * Subscribe to workspace events while the component is mounted.
 *
 * `onEvent` receives the events whose type is in `types`; `onConnect` runs
 * on the first connection and on every reconnection.
 */
export function useWorkspaceEvents(
    types: readonly ControlEventType[],
    onEvent: (event: ControlEvent) => void,
    onConnect?: () => void,
): ConnectionState {
    const [state, setState] = useState<ConnectionState>("connecting");

    // The latest callbacks, without reopening the stream when they change.
    const handlers = useRef({ types, onEvent, onConnect });
    useEffect(() => {
        handlers.current = { types, onEvent, onConnect };
    });

    useEffect(() => {
        if (typeof EventSource === "undefined") {
            return;
        }

        const source = new EventSource(workspaceEventsUrl(), { withCredentials: true });

        source.onopen = () => {
            setState("live");
            handlers.current.onConnect?.();
        };

        source.onerror = () => {
            setState("offline");
        };

        source.onmessage = (message) => {
            const event = parseEvent(message.data);
            const { types: wanted, onEvent: handle } = handlers.current;

            if (event && (wanted as readonly string[]).includes(event.type)) {
                handle(event);
            }
        };

        return () => source.close();
    }, []);

    return state;
}

// Bursts of events (a run moving through its states) cause one refresh.
export const REFRESH_DEBOUNCE_MS = 250;

/**
 * Re-read a page's data when one of `types` arrives (and `accept` agrees),
 * at most once per burst, and on every (re)connection.
 */
export function useLiveRefresh(
    refresh: () => void,
    types: readonly ControlEventType[],
    accept?: (event: ControlEvent) => boolean,
): ConnectionState {
    const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

    const schedule = useCallback(() => {
        if (timer.current) {
            clearTimeout(timer.current);
        }
        timer.current = setTimeout(() => {
            timer.current = null;
            refresh();
        }, REFRESH_DEBOUNCE_MS);
    }, [refresh]);

    useEffect(
        () => () => {
            if (timer.current) {
                clearTimeout(timer.current);
            }
        },
        [],
    );

    return useWorkspaceEvents(
        types,
        (event) => {
            if (!accept || accept(event)) {
                schedule();
            }
        },
        schedule,
    );
}
