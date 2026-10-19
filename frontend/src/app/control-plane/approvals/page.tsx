/**
 * @file frontend/src/app/control-plane/approvals/page.tsx
 * @description Human-in-the-loop approval queue (spec 3.4).
 *
 * Lists the pending approval requests of the caller's workspace from
 * GET /api/approvals and decides them with POST /api/approvals/{id}.
 * Each decision covers one exact tool call: there is no "always allow".
 * Requests left undecided past their TTL are denied by the backend.
 */
"use client";

import React, { useCallback, useEffect, useState } from "react";

import { getJson, postJson } from "@/lib/api/client";

interface ApprovalRequest {
    id: string;
    run_id: string | null;
    session_id: string;
    tool: string;
    risk: string;
    arguments_hash: string;
    requested_by: string;
    requested_at: string;
    expires_at: string;
}

type Decision = "allow" | "deny";

const REFRESH_INTERVAL_MS = 5000;

// Backend timestamps are naive UTC.
function secondsLeft(expiresAt: string, now: number): number {
    const expires = Date.parse(expiresAt.endsWith("Z") ? expiresAt : `${expiresAt}Z`);
    return Math.max(0, Math.round((expires - now) / 1000));
}

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

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        const poll = setInterval(refresh, REFRESH_INTERVAL_MS);
        const tick = setInterval(() => setNow(Date.now()), 1000);
        return () => {
            clearTimeout(first);
            clearInterval(poll);
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
        <div className="p-8 text-white min-h-screen" style={{ backgroundColor: "#111" }}>
            <h1 className="text-3xl font-bold mb-6 text-orange-500">Control Plane: Human Approvals</h1>

            {error && <p className="mb-4 text-red-400">{error}</p>}

            {approvals.length === 0 ? (
                <p className="text-gray-400">No pending approvals.</p>
            ) : (
                <table className="w-full text-left border-collapse">
                    <thead>
                        <tr className="border-b border-gray-700">
                            <th className="p-2">Tool</th>
                            <th className="p-2">Risk</th>
                            <th className="p-2">Run</th>
                            <th className="p-2">Requested by</th>
                            <th className="p-2">Expires in</th>
                            <th className="p-2">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {approvals.map((item) => {
                            const remaining = secondsLeft(item.expires_at, now);
                            const disabled = busyId === item.id || remaining === 0;

                            return (
                                <tr key={item.id} className="border-b border-gray-800">
                                    <td className="p-2 font-mono">{item.tool}</td>
                                    <td className="p-2 text-yellow-500 uppercase">{item.risk}</td>
                                    <td className="p-2 text-gray-400 font-mono">{item.run_id ?? "-"}</td>
                                    <td className="p-2">{item.requested_by}</td>
                                    <td className="p-2">{remaining > 0 ? `${remaining}s` : "expired"}</td>
                                    <td className="p-2">
                                        <button
                                            onClick={() => decide(item.id, "allow")}
                                            disabled={disabled}
                                            className="bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white px-4 py-1 rounded"
                                        >
                                            Allow once
                                        </button>
                                        <button
                                            onClick={() => decide(item.id, "deny")}
                                            disabled={disabled}
                                            className="bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white px-4 py-1 rounded ml-2"
                                        >
                                            Deny
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            )}
        </div>
    );
}
