/**
 * @file frontend/tests/notify.test.tsx
 * @description Approvals are not missed (ADR-037): the tab title counts them,
 * a system notification calls the owner when they would not see the card,
 * and APPROVAZIONI turns the notifications on.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ApprovalsPage from "@/app/control-plane/approvals/page";
import { notificationBody } from "@/components/interface/ApprovalNotifier";
import InterfaceProvider from "@/components/interface/InterfaceProvider";
import { showsApprovals, titleWithCount } from "@/lib/notify";

import { FakeEventSource, installEventSource, stubFetch } from "./helpers";

const PENDING = {
    id: "appr-1",
    run_id: "run-1",
    session_id: "s",
    tool: "delete_path",
    risk: "high",
    arguments_hash: "abc",
    arguments: { path: "C:\\Users\\me\\Documenti\\vecchio.txt" },
    requested_by: "owner",
    requested_at: "2026-11-26T10:00:00",
    expires_at: new Date(Date.now() + 5 * 60_000).toISOString().replace("Z", ""),
};

class FakeNotification {
    static permission: NotificationPermission = "granted";
    static shown: FakeNotification[] = [];
    static requestPermission = vi.fn(async () => {
        FakeNotification.permission = "granted";
        return "granted" as NotificationPermission;
    });
    closed = false;
    onclick: (() => void) | null = null;
    onclose: (() => void) | null = null;
    constructor(
        readonly title: string,
        readonly options: NotificationOptions
    ) {
        FakeNotification.shown.push(this);
    }
    close() {
        this.closed = true;
    }
}

function installNotification(permission: NotificationPermission) {
    FakeNotification.permission = permission;
    FakeNotification.shown = [];
    vi.stubGlobal("Notification", FakeNotification);
}

function stream() {
    return FakeEventSource.instances.find((source) => source.url.includes("scope=workspace"))!;
}

describe("approval notifications", () => {
    beforeEach(() => {
        document.title = "ÆHub";
    });

    it("counts in the title and knows which pages show the card", () => {
        expect(titleWithCount("ÆHub", 2)).toBe("(2) ÆHub");
        expect(titleWithCount("(2) ÆHub", 0)).toBe("ÆHub");
        expect(titleWithCount("(2) ÆHub", 1)).toBe("(1) ÆHub");
        expect(showsApprovals("/")).toBe(true);
        expect(showsApprovals("/control-plane/approvals/")).toBe(true);
        expect(showsApprovals("/control-plane/settings/")).toBe(false);
    });

    it("writes the call, its arguments and the time left", () => {
        const body = notificationBody(PENDING, Date.now(), (minutes) => `in ${minutes} min`);
        expect(body).toBe(
            "delete_path · HIGH\npath: C:\\Users\\me\\Documenti\\vecchio.txt\nin 5 min"
        );
    });

    it("notifies an approval the owner would miss, and closes it once decided", async () => {
        installEventSource();
        installNotification("granted");
        let pending = [PENDING];
        stubFetch({
            "GET /api/approvals": () => ({ status: 200, body: pending }),
            "GET /api/interface": () => ({ status: 401, body: { detail: "no" } }),
        });
        // The window is behind another one.
        vi.spyOn(document, "hasFocus").mockReturnValue(false);

        render(<InterfaceProvider />);
        act(() => stream().open());
        await waitFor(() => expect(document.title).toBe("(1) ÆHub"));

        act(() =>
            stream().emit("approval.requested", {
                approval_id: "appr-1",
                run_id: "run-1",
                tool: "delete_path",
            })
        );
        await waitFor(() => expect(FakeNotification.shown).toHaveLength(1));
        const [shown] = FakeNotification.shown;
        expect(shown.title).toBe("ÆHub · approval requested");
        expect(shown.options.body).toContain("vecchio.txt");
        expect(shown.options.requireInteraction).toBe(true);

        pending = [];
        act(() =>
            stream().emit("approval.decided", {
                approval_id: "appr-1",
                run_id: "run-1",
                decision: "ALLOW",
            })
        );
        await waitFor(() => expect(shown.closed).toBe(true));
        await waitFor(() => expect(document.title).toBe("ÆHub"));
    });

    it("does not notify when the owner is looking at the card", async () => {
        installEventSource();
        installNotification("granted");
        stubFetch({
            "GET /api/approvals": () => ({ status: 200, body: [PENDING] }),
            "GET /api/interface": () => ({ status: 401, body: { detail: "no" } }),
        });
        vi.spyOn(document, "hasFocus").mockReturnValue(true);
        vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");

        render(<InterfaceProvider />);
        act(() =>
            stream().emit("approval.requested", {
                approval_id: "appr-1",
                run_id: "run-1",
                tool: "delete_path",
            })
        );
        await waitFor(() => expect(document.title).toBe("(1) ÆHub"));
        expect(FakeNotification.shown).toHaveLength(0);
    });

    it("turns the notifications on from APPROVAZIONI", async () => {
        installEventSource();
        installNotification("default");
        stubFetch({ "GET /api/approvals": () => ({ status: 200, body: [] }) });

        render(<ApprovalsPage />);
        await userEvent.click(await screen.findByRole("button", { name: "Turn on notifications" }));

        expect(FakeNotification.requestPermission).toHaveBeenCalled();
        expect(await screen.findByText(/System notifications are on/)).toBeInTheDocument();
        expect(screen.getByText(/answer Aurora in a word/)).toBeInTheDocument();
    });
});
