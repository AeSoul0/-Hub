/**
 * @file frontend/src/app/control-plane/approvals/page.tsx
 * @description Human-in-the-loop approval queue (spec 3.4).
 *
 * Lists the pending approval requests of the caller's workspace from
 * GET /api/approvals and decides them with POST /api/approvals/{id}.
 * Each decision covers one exact tool call, whose arguments are shown:
 * there is no "always allow". Requests left undecided past their TTL are
 * denied by the backend. The list is re-read on live workspace events
 * (approval requested or decided), not on a timer.
 */
"use client";

import React, { useCallback, useEffect, useState } from "react";

import ApprovalCard, { type ApprovalRequest, type Decision } from "@/components/control-plane/ApprovalCard";
import LiveBadge from "@/components/control-plane/LiveBadge";
import styles from "@/components/control-plane/control.module.css";
import { getJson, postJson } from "@/lib/api/client";
import { useLiveRefresh } from "@/lib/api/events";
import { catalog, useText } from "@/lib/i18n";
import { askNotifyPermission, notifyState, type NotifyState } from "@/lib/notify";

const TEXT = catalog({
    en: {
        title: "APPROVALS",
        intro: "Each decision covers one call only, with the arguments shown: there is no permanent consent. Without an answer, the call is denied when it expires.",
        none: "No approval waiting.",
        notify: {
            granted: "System notifications are on: a request reaches you even with ÆHub minimized.",
            default: "Turn on the system notifications to see a request even with ÆHub minimized.",
            denied: "The browser blocks the notifications of ÆHub: allow them in the site settings (the icon left of the address).",
            unsupported: "This window cannot show system notifications: the tab title counts the requests.",
        },
        enable: "Turn on notifications",
        voice: "You can also answer Aurora in a word: \"yes\", \"go ahead\", \"no\", \"cancel\".",
    },
    it: {
        title: "APPROVAZIONI",
        intro: "Ogni decisione vale per una sola chiamata, con gli argomenti mostrati: non esiste un consenso permanente. Senza risposta, alla scadenza la chiamata viene negata.",
        none: "Nessuna approvazione in attesa.",
        notify: {
            granted: "Le notifiche del sistema sono attive: una richiesta ti arriva anche con ÆHub ridotto a icona.",
            default: "Attiva le notifiche del sistema per vedere una richiesta anche con ÆHub ridotto a icona.",
            denied: "Il browser blocca le notifiche di ÆHub: consentile dalle impostazioni del sito (l'icona a sinistra dell'indirizzo).",
            unsupported: "Questa finestra non può mostrare notifiche del sistema: il titolo della scheda conta le richieste.",
        },
        enable: "Attiva le notifiche",
        voice: "Puoi anche rispondere ad Aurora con una parola: \"sì\", \"vai pure\", \"no\", \"annulla\".",
    },
});

// Renders the approvals interface where users can decide pending tool calls
export default function ApprovalsPage() {
    const t = useText(TEXT);
    const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [busyId, setBusyId] = useState<string | null>(null);
    const [now, setNow] = useState(() => Date.now());
    const [notify, setNotify] = useState<NotifyState>("unsupported");

    useEffect(() => {
        const read = setTimeout(() => setNotify(notifyState()), 0);
        return () => clearTimeout(read);
    }, []);

    const refresh = useCallback(async () => {
        try {
            setApprovals(await getJson<ApprovalRequest[]>("/api/approvals"));
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        }
    }, []);

    const live = useLiveRefresh(refresh, ["approval.requested", "approval.decided"]);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        // Only the countdown ticks; the data comes from events.
        const tick = setInterval(() => setNow(Date.now()), 1000);
        return () => {
            clearTimeout(first);
            clearInterval(tick);
        };
    }, [refresh]);

    const decide = async (id: string, decision: Decision) => {
        setBusyId(id);
        try {
            await postJson(`/api/approvals/${encodeURIComponent(id)}`, { decision });
            setApprovals((current) => current.filter((item) => item.id !== id));
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
            await refresh();
        } finally {
            setBusyId(null);
        }
    };

    return (
        <div className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>{t.title}</h1>
                <LiveBadge state={live} />
            </div>

            <p className={styles.muted}>{t.intro}</p>
            <p className={styles.help}>{t.voice}</p>
            <div className={styles.row}>
                <p className={styles.help}>{t.notify[notify]}</p>
                {notify === "default" && (
                    <button
                        type="button"
                        className={styles.btn}
                        onClick={async () => setNotify(await askNotifyPermission())}
                    >
                        {t.enable}
                    </button>
                )}
            </div>

            {error && <p className={styles.error}>{error}</p>}

            {approvals.length === 0 ? (
                <p className={styles.muted}>{t.none}</p>
            ) : (
                <div className={styles.stack}>
                    {approvals.map((item) => (
                        <ApprovalCard
                            key={item.id}
                            item={item}
                            now={now}
                            busy={busyId === item.id}
                            onDecide={decide}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}
