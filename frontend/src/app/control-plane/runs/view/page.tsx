/**
 * @file frontend/src/app/control-plane/runs/view/page.tsx
 * @description One agent run: task, state, totals against the limits, the
 * call waiting for approval, its timeline, what each tool returned and the
 * audit trail (M11, F2).
 *
 * /control-plane/runs/view?id=<run id>: the id is in the query string so the
 * page also works as a static file in the desktop app (M14).
 * Reads GET /api/runs/{id} and GET /api/runs/{id}/events, again when this
 * run changes state. Untrusted observations (web pages, files, MCP output)
 * are marked: they were data for the model, never instructions.
 */
"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import React, { Suspense, useCallback, useEffect, useState } from "react";

import LiveBadge from "@/components/control-plane/LiveBadge";
import RunDetailView, { type RunDetail } from "@/components/control-plane/RunDetailView";
import RunTimeline, { type Timeline } from "@/components/control-plane/RunTimeline";
import styles from "@/components/control-plane/control.module.css";
import { ApiError, getJson, postJson } from "@/lib/api/client";
import { useLiveRefresh } from "@/lib/api/events";

export default function RunPage() {
    // The query string is known only in the browser: a static export needs
    // the boundary to prerender the rest of the page.
    return (
        <Suspense>
            <RunView />
        </Suspense>
    );
}

function RunView() {
    const runId = useSearchParams()?.get("id") ?? "";

    const [run, setRun] = useState<RunDetail | null>(null);
    const [timeline, setTimeline] = useState<Timeline | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [missing, setMissing] = useState(false);

    const refresh = useCallback(async () => {
        if (!runId) {
            return;
        }
        const path = `/api/runs/${encodeURIComponent(runId)}`;
        try {
            const [detail, events] = await Promise.all([getJson<RunDetail>(path), getJson<Timeline>(`${path}/events`)]);
            setRun(detail);
            setTimeline(events);
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
        ["run.state", "run.resumed", "approval.decided", "approval.requested", "engine.event"],
        (event) => event.data.run_id === runId || event.data.parent_run_id === runId,
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
        <div className={styles.page}>
            <Link href="/control-plane/runs" className={styles.back}>
                ← TUTTE LE RUN
            </Link>
            <div className={styles.head}>
                <h1 className={`${styles.title} ${styles.runTitle}`}>
                    {runId || "RUN"}
                </h1>
                <LiveBadge state={live} />
            </div>

            {error && <p className={styles.error}>{error}</p>}
            {!runId && <p className={styles.muted}>Nessuna run selezionata.</p>}
            {missing && <p className={styles.muted}>Nessuna run con questo id nel tuo workspace.</p>}
            {run && (
                <RunDetailView
                    run={run}
                    limits={timeline?.limits ?? null}
                    onCancel={cancel}
                    timeline={
                        timeline && (
                            <section className={styles.section} aria-labelledby="timeline-title">
                                <h2 id="timeline-title" className={styles.h2}>
                                    TIMELINE <span>{timeline.events.length}</span>
                                </h2>
                                <RunTimeline timeline={timeline} />
                            </section>
                        )
                    }
                />
            )}
        </div>
    );
}
