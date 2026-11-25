/**
 * @file frontend/src/components/control-plane/RunTimeline.tsx
 * @description The timeline of one run from its recorded events
 * (GET /api/runs/{id}/events, F2): when each step happened from the start,
 * and the run's cost so far.
 */
import React from "react";

import { catalog, useLanguage } from "@/lib/i18n";
import type { EngineEvent } from "@/lib/nucleo/engine";
import { offset, replay, usd, type RunLimits } from "@/lib/nucleo/runs";

import styles from "./control.module.css";

export interface Timeline {
    run_id: string;
    truncated: boolean;
    events: EngineEvent[];
    limits: RunLimits;
}

const TEXT = catalog({
    en: {
        empty: "No event recorded for this run.",
        truncated: "Only the most recent events.",
        timeline: "Timeline of the run",
    },
    it: {
        empty: "Nessun evento registrato per questa run.",
        truncated: "Solo gli eventi più recenti.",
        timeline: "Timeline della run",
    },
});

export default function RunTimeline({ timeline }: { timeline: Timeline }) {
    const lang = useLanguage();
    const t = TEXT[lang];
    const run = replay(timeline.run_id, timeline.events, lang);

    if (!run || run.steps.length === 0) {
        return <p className={styles.muted}>{t.empty}</p>;
    }

    return (
        <div className={styles.card}>
            {timeline.truncated && <p className={styles.muted}>{t.truncated}</p>}
            <ol className={styles.timeline} aria-label={t.timeline}>
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
