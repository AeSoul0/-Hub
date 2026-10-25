/**
 * @file frontend/src/components/control-plane/RunTimeline.tsx
 * @description The timeline of one run from its recorded events
 * (GET /api/runs/{id}/events, F2): when each step happened from the start,
 * and the run's cost so far.
 */
import React from "react";

import type { EngineEvent } from "@/lib/nucleo/engine";
import { offset, replay, usd, type RunLimits } from "@/lib/nucleo/runs";

import styles from "./control.module.css";

export interface Timeline {
    run_id: string;
    truncated: boolean;
    events: EngineEvent[];
    limits: RunLimits;
}

export default function RunTimeline({ timeline }: { timeline: Timeline }) {
    const run = replay(timeline.run_id, timeline.events);

    if (!run || run.steps.length === 0) {
        return <p className={styles.muted}>Nessun evento registrato per questa run.</p>;
    }

    return (
        <div className={styles.card}>
            {timeline.truncated && <p className={styles.muted}>Solo gli eventi più recenti.</p>}
            <ol className={styles.timeline} aria-label="Timeline della run">
                {run.steps.map((step) => (
                    <li key={step.id} data-k={step.kind}>
                        <time>{offset(step, run)}</time>
                        <span className={styles.tick} aria-hidden="true" />
                        <span>
                            <span className={styles.stepName}>{step.name}</span>
                            {step.detail && <span className={styles.stepDetail}>{step.detail}</span>}
                        </span>
                        <span className={styles.stepTotal}>{step.total != null ? `Σ ${usd(step.total)}` : ""}</span>
                    </li>
                ))}
            </ol>
        </div>
    );
}
