/**
 * @file frontend/src/app/control-plane/runs/[runId]/page.tsx
 * @description One agent run: task, state, cost, the call waiting for
 * approval, what each tool returned and the audit trail (M11).
 *
 * Reads GET /api/runs/{id} and re-reads it when this run changes state.
 * Untrusted observations (web pages, files, MCP output) are marked: they
 * were data for the model, never instructions.
 */
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import React, { useCallback, useEffect, useState } from "react";

import LiveBadge from "@/components/control-plane/LiveBadge";
import RunDetailView, { type RunDetail } from "@/components/control-plane/RunDetailView";
import { ApiError, getJson, postJson } from "@/lib/api/client";
import { useLiveRefresh } from "@/lib/api/events";

export default function RunPage() {
    const params = useParams<{ runId: string }>();
    const runId = decodeURIComponent(params?.runId ?? "");

    const [run, setRun] = useState<RunDetail | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [missing, setMissing] = useState(false);

    const refresh = useCallback(async () => {
        if (!runId) {
            return;
        }
        try {
            setRun(await getJson<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`));
            setMissing(false);
            setError(null);
        } catch (err) {
            if (err instanceof ApiError && err.status === 404) {
                setMissing(true);
            } else {
                setError(err instanceof Error ? err.message : String(err));
            }
        }
    }, [runId]);

    const live = useLiveRefresh(
        refresh,
        ["run.state", "run.resumed", "approval.decided", "approval.requested"],
        (event) => event.data.run_id === runId,
    );

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    const cancel = async () => {
        try {
            await postJson(`/api/runs/${encodeURIComponent(runId)}/cancel`, {});
            await refresh();
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        }
    };

    return (
        <div className="p-8">
            <Link href="/control-plane/runs" className="text-cyan-400 hover:underline text-sm">
                ← All runs
            </Link>
            <div className="flex flex-wrap items-center gap-4 mt-2 mb-6">
                <h1 className="text-2xl font-bold text-orange-500 font-mono break-all">{runId}</h1>
                <LiveBadge state={live} />
            </div>

            {error && <p className="mb-4 text-red-400">{error}</p>}
            {missing && <p className="text-gray-400">No run with this id in your workspace.</p>}
            {run && <RunDetailView run={run} onCancel={cancel} />}
        </div>
    );
}
