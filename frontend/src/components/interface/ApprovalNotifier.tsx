/**
 * @file frontend/src/components/interface/ApprovalNotifier.tsx
 * @description Approvals are not missed (ADR-037), on every page.
 *
 * - The tab title counts the pending approvals: "(1) ÆHub".
 * - When an approval is requested and the owner would not see it (the window
 *   is minimized, behind another one, or on a page without the approval
 *   card), a system notification shows the call and its arguments. A click
 *   brings ÆHub to the front, on the Nucleo; it closes once decided.
 *
 * The decision itself stays on the card (Nucleo, APPROVAZIONI) or in a word
 * to Aurora: the notification only calls the owner.
 */
"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { type ApprovalRequest, secondsLeft } from "@/components/control-plane/ApprovalCard";
import { formatArguments } from "@/components/nucleo/ApprovalPrompt";
import { getJson } from "@/lib/api/client";
import type { ControlEvent } from "@/lib/api/events";
import { catalog, useLanguage } from "@/lib/i18n";
import { notifyState, showsApprovals, titleWithCount, wouldMiss } from "@/lib/notify";

const BODY_LIMIT = 180;

const TEXT = catalog({
    en: {
        title: "ÆHub · approval requested",
        expires: (minutes: number) =>
            `Expires in ${minutes} min. Decide in ÆHub, or tell Aurora yes or no.`,
    },
    it: {
        title: "ÆHub · approvazione richiesta",
        expires: (minutes: number) =>
            `Scade tra ${minutes} min. Decidi in ÆHub, o di' ad Aurora sì o no.`,
    },
});

export function notificationBody(
    item: ApprovalRequest,
    now: number,
    expires: (minutes: number) => string
): string {
    const args = item.arguments ? formatArguments(item.arguments) : "";
    const what = `${item.tool} · ${item.risk.toUpperCase()}${args ? `\n${args}` : ""}`;
    const short = what.length > BODY_LIMIT ? `${what.slice(0, BODY_LIMIT - 1)}…` : what;
    const minutes = Math.max(1, Math.round(secondsLeft(item.expires_at, now) / 60));
    return `${short}\n${expires(minutes)}`;
}

export const APPROVAL_EVENTS = ["approval.requested", "approval.decided"] as const;

/**
 * The approval notices of every page. InterfaceProvider feeds them from its
 * own workspace stream, so a page keeps a single connection for both.
 */
export function useApprovalNotices(): {
    onEvent: (event: ControlEvent) => void;
    onConnect: () => void;
} {
    const pathname = usePathname();
    const lang = useLanguage();
    const [count, setCount] = useState(0);
    const shown = useRef(new Map<string, Notification>());
    const where = useRef(pathname);
    const langRef = useRef(lang);

    useEffect(() => {
        where.current = pathname;
        langRef.current = lang;
    });

    const pending = useCallback(async (): Promise<ApprovalRequest[] | null> => {
        try {
            const items = await getJson<ApprovalRequest[]>("/api/approvals");
            setCount(items.length);
            return items;
        } catch {
            // Not logged in, or the API is down: nothing to count.
            return null;
        }
    }, []);

    const close = useCallback((id: string) => {
        shown.current.get(id)?.close();
        shown.current.delete(id);
    }, []);

    const notify = useCallback(
        async (id: string) => {
            const items = await pending();
            const item = items?.find((candidate) => candidate.id === id);
            if (!item || notifyState() !== "granted" || !wouldMiss(where.current)) {
                return;
            }
            const t = TEXT[langRef.current];
            try {
                const notification = new Notification(t.title, {
                    body: notificationBody(item, Date.now(), t.expires),
                    tag: `aehub-approval-${item.id}`,
                    requireInteraction: true,
                });
                notification.onclick = () => {
                    window.focus();
                    if (!showsApprovals(where.current)) {
                        // Outside the router (root layout, every page): a plain load of the Nucleo.
                        window.location.assign(new URL("/", window.location.href).toString());
                    }
                    notification.close();
                };
                notification.onclose = () => shown.current.delete(item.id);
                shown.current.set(item.id, notification);
                // An approval left to expire is denied: its notification goes too.
                setTimeout(
                    () => close(item.id),
                    secondsLeft(item.expires_at, Date.now()) * 1000 + 1000
                );
            } catch {
                // Some webviews have the API but refuse to show: the title still counts.
            }
        },
        [pending, close]
    );

    const onEvent = useCallback(
        (event: ControlEvent) => {
            const id = String(event.data.approval_id ?? "");
            if (event.type === "approval.requested" && id) {
                void notify(id);
                return;
            }
            if (id) {
                close(id);
            }
            void pending();
        },
        [notify, close, pending]
    );
    const onConnect = useCallback(() => void pending(), [pending]);

    // Next sets the title on navigation: count again after it.
    useEffect(() => {
        const timer = setTimeout(() => {
            document.title = titleWithCount(document.title, count);
        }, 0);
        return () => clearTimeout(timer);
    }, [count, pathname]);

    useEffect(() => {
        const open = shown.current;
        return () => open.forEach((notification) => notification.close());
    }, []);

    return { onEvent, onConnect };
}
