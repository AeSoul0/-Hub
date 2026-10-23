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
import { getJson, postJson } from "@/lib/api/client";
import { useLiveRefresh } from "@/lib/api/events";

// Renders the approvals interface where users can decide pending tool calls
export default function ApprovalsPage() {
    const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [busyId, setBusyId] = useState<string | null>(null);
    const [now, setNow] = useState(() => Date.now());

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
        <div className="p-8">
            <div className="flex items-center gap-4 mb-6">
                <h1 className="text-3xl font-bold text-orange-500">Human Approvals</h1>
                <LiveBadge state={live} />
            </div>

            {error && <p className="mb-4 text-red-400">{error}</p>}

            {approvals.length === 0 ? (
                <p className="text-gray-400">No pending approvals.</p>
            ) : (
                <div className="space-y-4">
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
