/**
 * @file frontend/src/lib/notify.ts
 * @description System notifications for approvals (ADR-037).
 *
 * The browser's Notification API: on localhost it is a secure context, so it
 * works with the backend on the PC. The permission is asked once, on a click
 * (the first command sent in the Nucleo, or the button on APPROVAZIONI);
 * browsers ignore a request that does not come from a click.
 */

export type NotifyState = "granted" | "default" | "denied" | "unsupported";

const ASKED_KEY = "aehub.notify-asked";

export function notifyState(): NotifyState {
    if (typeof window === "undefined" || typeof window.Notification === "undefined") {
        return "unsupported";
    }
    return window.Notification.permission as NotifyState;
}

/** Ask for the permission; call it only from a click. */
export async function askNotifyPermission(): Promise<NotifyState> {
    if (notifyState() !== "default") {
        return notifyState();
    }
    try {
        window.localStorage.setItem(ASKED_KEY, "1");
    } catch {
        // Storage refused: the question may come again on the next command.
    }
    try {
        return (await window.Notification.requestPermission()) as NotifyState;
    } catch {
        return notifyState();
    }
}

/** Ask once, on the first command sent from the Nucleo; later only from APPROVAZIONI. */
export function askNotifyPermissionOnce(): void {
    if (notifyState() !== "default") {
        return;
    }
    try {
        if (window.localStorage.getItem(ASKED_KEY)) {
            return;
        }
    } catch {
        // No storage: ask, the browser remembers the answer anyway.
    }
    void askNotifyPermission();
}

/** Pages that show the pending approval themselves. */
export function showsApprovals(pathname: string | null): boolean {
    const path = pathname ?? "";
    return path === "/" || path === "" || path.startsWith("/control-plane/approvals");
}

/** Whether the owner would miss an approval without a system notification. */
export function wouldMiss(pathname: string | null): boolean {
    if (typeof document === "undefined") {
        return false;
    }
    const looking = document.visibilityState === "visible" && document.hasFocus();
    return !(looking && showsApprovals(pathname));
}

const TITLE_COUNT = /^\(\d+\)\s*/;

/** "(2) ÆHub" while approvals wait; the plain title otherwise. */
export function titleWithCount(title: string, count: number): string {
    const plain = title.replace(TITLE_COUNT, "");
    return count > 0 ? `(${count}) ${plain}` : plain;
}
