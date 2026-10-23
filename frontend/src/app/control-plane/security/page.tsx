/**
 * @file frontend/src/app/control-plane/security/page.tsx
 * @description Audit trail of the workspace and integrity of its hash chain.
 *
 * GET /api/audit returns the latest tool calls recorded by the Tool Gateway
 * (who, which tool, risk, policy decision, outcome) and re-verifies the
 * append-only hash chain: a deleted or modified audit row shows up here.
 * The list follows live run events.
 */
"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useState } from "react";

import LiveBadge from "@/components/control-plane/LiveBadge";
import type { AuditEntry } from "@/components/control-plane/RunDetailView";
import { getJson } from "@/lib/api/client";
import { useLiveRefresh } from "@/lib/api/events";

interface AuditView {
    entries: AuditEntry[];
    chain: {
        valid: boolean;
        checked: number;
        broken_at_seq: number | null;
        reason: string | null;
    };
}

// Decisions the Tool Gateway records (EXECUTING is written before the tool
// runs: audit is fail-closed).
const DECISIONS = ["", "ALLOW", "DENY", "EXECUTING", "CACHED", "ERROR", "CANCELLED"] as const;

export default function SecurityPage() {
    const [view, setView] = useState<AuditView | null>(null);
    const [decision, setDecision] = useState<(typeof DECISIONS)[number]>("");
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        try {
            setView(
                await getJson<AuditView>("/api/audit", {
                    params: decision ? { decision, limit: 200 } : { limit: 200 },
                }),
            );
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        }
    }, [decision]);

    const live = useLiveRefresh(refresh, ["run.state", "run.resumed", "approval.decided"]);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    const chain = view?.chain;

    return (
        <div className="p-8">
            <div className="flex items-center gap-4 mb-6">
                <h1 className="text-3xl font-bold text-orange-500">Security Audit</h1>
                <LiveBadge state={live} />
            </div>

            {error && <p className="mb-4 text-red-400">{error}</p>}

            {chain && (
                <p
                    role="status"
                    className={`mb-6 font-semibold ${chain.valid ? "text-green-400" : "text-red-400"}`}
                >
                    {chain.valid
                        ? `Audit chain intact (${chain.checked} records verified).`
                        : `Audit chain BROKEN at record ${chain.broken_at_seq}: ${chain.reason}.`}
                </p>
            )}

            <label className="flex items-center gap-2 mb-4 text-sm">
                Decision
                <select
                    value={decision}
                    onChange={(event) => setDecision(event.target.value as (typeof DECISIONS)[number])}
                    className="bg-gray-900 border border-gray-700 rounded px-2 py-1"
                >
                    {DECISIONS.map((item) => (
                        <option key={item} value={item}>
                            {item || "all"}
                        </option>
                    ))}
                </select>
            </label>

            {view && view.entries.length === 0 ? (
                <p className="text-gray-400">No audited tool call.</p>
            ) : (
                <table className="w-full text-left border-collapse text-sm">
                    <thead>
                        <tr className="border-b border-gray-700">
                            <th className="p-2">Time</th>
                            <th className="p-2">Tool</th>
                            <th className="p-2">Risk</th>
                            <th className="p-2">Decision</th>
                            <th className="p-2">Result</th>
                            <th className="p-2">Run</th>
                        </tr>
                    </thead>
                    <tbody>
                        {view?.entries.map((entry) => (
                            <tr key={entry.id} className="border-b border-gray-800 align-top">
                                <td className="p-2 text-gray-400 whitespace-nowrap">{entry.timestamp}</td>
                                <td className="p-2 font-mono">{entry.tool_name}</td>
                                <td className="p-2 uppercase">{entry.risk}</td>
                                <td className="p-2">{entry.decision ?? "-"}</td>
                                <td className={`p-2 ${entry.success ? "text-green-400" : "text-red-400"}`}>
                                    {entry.success ? "ok" : (entry.error ?? "failed")}
                                </td>
                                <td className="p-2 font-mono">
                                    {entry.run_id ? (
                                        <Link
                                            href={`/control-plane/runs/${encodeURIComponent(entry.run_id)}`}
                                            className="text-cyan-400 hover:underline"
                                        >
                                            {entry.run_id.slice(0, 16)}
                                        </Link>
                                    ) : (
                                        "-"
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}
