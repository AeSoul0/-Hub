import { vi } from "vitest";

/**
 * Stub global fetch with one handler per "METHOD path"; anything else is a
 * test failure. Returns the mock to inspect the calls.
 */
export function stubFetch(routes: Record<string, () => { status: number; body: unknown }>) {
    const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const key = `${init?.method ?? "GET"} ${url.pathname}`;
        const route = routes[key];

        if (!route) {
            throw new Error(`Unexpected request: ${key}`);
        }

        const { status, body } = route();

        return new Response(JSON.stringify(body), {
            status,
            headers: { "Content-Type": "application/json" },
        });
    });

    vi.stubGlobal("fetch", mock);
    return mock;
}

/**
 * Minimal EventSource double: tests drive open, messages and errors.
 */
export class FakeEventSource {
    static instances: FakeEventSource[] = [];

    readonly url: string;
    readonly withCredentials: boolean;
    closed = false;
    onopen: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((message: { data: string }) => void) | null = null;

    constructor(url: string, init?: { withCredentials?: boolean }) {
        this.url = url;
        this.withCredentials = Boolean(init?.withCredentials);
        FakeEventSource.instances.push(this);
    }

    open() {
        this.onopen?.();
    }

    emit(type: string, data: Record<string, unknown>) {
        this.onmessage?.({ data: JSON.stringify({ type, data }) });
    }

    fail() {
        this.onerror?.();
    }

    close() {
        this.closed = true;
    }
}

export function installEventSource() {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    return FakeEventSource;
}
