import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { parseEvent, REFRESH_DEBOUNCE_MS, useLiveRefresh, useWorkspaceEvents } from "@/lib/api/events";

import { installEventSource } from "./helpers";

describe("parseEvent", () => {
    it("reads bus messages", () => {
        expect(parseEvent('{"type":"run.state","data":{"run_id":"r1","state":"planning"}}')).toEqual({
            type: "run.state",
            data: { run_id: "r1", state: "planning" },
        });
    });

    it("rejects what is not an event", () => {
        expect(parseEvent("not json")).toBeNull();
        expect(parseEvent('{"data":{}}')).toBeNull();
        expect(parseEvent('{"type":"log","data":"text"}')).toEqual({ type: "log", data: {} });
    });
});

describe("useWorkspaceEvents", () => {
    it("opens the workspace stream with the session cookie and filters by type", () => {
        const Source = installEventSource();
        const onEvent = vi.fn();
        const onConnect = vi.fn();

        const { result, unmount } = renderHook(() =>
            useWorkspaceEvents(["approval.requested"], onEvent, onConnect),
        );

        const source = Source.instances[0];
        expect(new URL(source.url).pathname).toBe("/api/events");
        expect(new URL(source.url).searchParams.get("scope")).toBe("workspace");
        expect(source.withCredentials).toBe(true);
        expect(result.current).toBe("connecting");

        act(() => source.open());
        expect(result.current).toBe("live");
        expect(onConnect).toHaveBeenCalledTimes(1);

        act(() => {
            source.emit("run.state", { run_id: "r1" });
            source.emit("approval.requested", { approval_id: "a1" });
        });
        expect(onEvent).toHaveBeenCalledTimes(1);
        expect(onEvent.mock.calls[0][0].data.approval_id).toBe("a1");

        act(() => source.fail());
        expect(result.current).toBe("offline");

        unmount();
        expect(source.closed).toBe(true);
    });
});

describe("useLiveRefresh", () => {
    it("refreshes once per burst of matching events and on reconnection", () => {
        vi.useFakeTimers();
        const Source = installEventSource();
        const refresh = vi.fn();

        renderHook(() =>
            useLiveRefresh(refresh, ["run.state"], (event) => event.data.run_id === "mine"),
        );
        const source = Source.instances[0];

        act(() => source.open());
        act(() => vi.advanceTimersByTime(REFRESH_DEBOUNCE_MS));
        expect(refresh).toHaveBeenCalledTimes(1);

        act(() => {
            source.emit("run.state", { run_id: "mine", state: "planning" });
            source.emit("run.state", { run_id: "mine", state: "tool_running" });
            source.emit("run.state", { run_id: "other", state: "done" });
        });
        act(() => vi.advanceTimersByTime(REFRESH_DEBOUNCE_MS));
        expect(refresh).toHaveBeenCalledTimes(2);

        act(() => source.emit("run.state", { run_id: "other", state: "done" }));
        act(() => vi.advanceTimersByTime(REFRESH_DEBOUNCE_MS));
        expect(refresh).toHaveBeenCalledTimes(2);
    });
});
