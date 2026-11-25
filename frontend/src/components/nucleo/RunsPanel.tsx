/**
 * @file frontend/src/components/nucleo/RunsPanel.tsx
 * @description The runs of this session in the Nucleo (F2): each one with
 * its totals against the per-run limits, a stop button and its timeline.
 */
"use client";

import Link from "next/link";
import React, { useEffect, useState } from "react";

import { runHref } from "@/lib/routes";
import { canStop, isEnded, meters, offset, ordered, STATUS_LABELS, usd, type RunsState } from "@/lib/nucleo/runs";

import styles from "./nucleo.module.css";
import { catalog, useLanguage } from "@/lib/i18n";

const TEXT = catalog({
    en: {
        empty: "Runs start from your commands: here you see cost, time and limits while they work.",
        history: "Run history",
        subagent: "SUBAGENT",
        limits: (id: string) => `Limits of run ${id}`,
        stop: "Stop the run",
        details: "Details →",
        timeline: (id: string) => `Timeline of run ${id}`,
        noEvents: "No event recorded.",
        waiting: "Waiting for the first event…",
    },
    it: {
        empty: "Le run partono dai tuoi comandi: qui vedi costo, tempo e limiti mentre lavorano.",
        history: "Storico delle run",
        subagent: "SUB-AGENTE",
        limits: (id: string) => `Limiti della run ${id}`,
        stop: "Ferma la run",
        details: "Dettagli →",
        timeline: (id: string) => `Timeline della run ${id}`,
        noEvents: "Nessun evento registrato.",
        waiting: "In attesa del primo evento…",
    },
});

const short = (id: string) => id.slice(0, 4);

/** Re-render once a second while a run's clock is running. */
function useClock(ticking: boolean): number {
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        if (!ticking) {
            return;
        }
        const timer = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(timer);
    }, [ticking]);
    // Only a running clock reads the time, so a stale value is harmless.
    return now;
}

export default function RunsPanel({
    state,
    onStop,
}: {
    state: RunsState;
    onStop: (runId: string) => void;
}) {
    const lang = useLanguage();
    const t = TEXT[lang];
    const runs = ordered(state.runs);
    const now = useClock(runs.some((run) => run.status === "running" || run.status === "cancelling"));
    // The newest run opens its timeline; the others on request.
    const [toggled, setToggled] = useState<Record<string, boolean>>({});

    if (runs.length === 0) {
        return (
            <div className={styles.stream}>
                <p className={styles.empty}>
                    {t.empty}{" "}
                    <Link className={styles.link} href="/control-plane/runs">
                        {t.history}
                    </Link>
                </p>
            </div>
        );
    }

    return (
        <ol className={styles.stream} aria-label="Run">
            {runs.map((run, index) => {
                const open = toggled[run.id] ?? index === 0;
                const timelineId = `timeline-${run.id}`;
                return (
                    <li key={run.id} className={`${styles.run} rise`} data-status={run.status} data-sub={run.parentId ? "" : undefined}>
                        <div className={styles.runHead}>
                            <span className={styles.runDot} aria-hidden="true" />
                            <b>
                                {run.parentId ? t.subagent : "RUN"} {short(run.id)}
                            </b>
                            <span className={styles.runStatus}>{STATUS_LABELS[lang][run.status]}</span>
                        </div>
                        {run.task && <p className={styles.runTask}>{run.task}</p>}

                        <ul className={styles.meters} aria-label={t.limits(short(run.id))}>
                            {meters(run, state.limits, now, lang).map((item) => (
                                <li key={item.key} data-level={item.level}>
                                    <span>{item.label}</span>
                                    <span className={styles.bar2} aria-hidden="true">
                                        <i style={{ width: `${item.ratio * 100}%` }} />
                                    </span>
                                    <span className={styles.meterText}>{item.text}</span>
                                </li>
                            ))}
                        </ul>

                        <div className={styles.row}>
                            {canStop(run) && (
                                <button type="button" className={`${styles.btn} ${styles.stop}`} onClick={() => onStop(run.id)}>
                                    {t.stop}
                                </button>
                            )}
                            <button
                                type="button"
                                className={styles.btn}
                                aria-expanded={open}
                                aria-controls={timelineId}
                                onClick={() => setToggled((current) => ({ ...current, [run.id]: !open }))}
                            >
                                Timeline {run.steps.length || ""}
                            </button>
                            <Link className={`${styles.link} ${styles.more}`} href={runHref(run.id)}>
                                {t.details}
                            </Link>
                        </div>

                        {open && (
                            <ol id={timelineId} className={styles.timeline} aria-label={t.timeline(short(run.id))}>
                                {run.steps.length === 0 ? (
                                    <li className={styles.empty}>{isEnded(run) ? t.noEvents : t.waiting}</li>
                                ) : (
                                    run.steps.map((step) => (
                                        <li key={step.id} data-k={step.kind}>
                                            <time>{offset(step, run)}</time>
                                            <span className={styles.evName}>{step.name}</span>
                                            {step.total != null && <span className={styles.total}>Σ {usd(step.total)}</span>}
                                            {step.detail && <span className={styles.evDetail}>{step.detail}</span>}
                                        </li>
                                    ))
                                )}
                            </ol>
                        )}
                    </li>
                );
            })}
        </ol>
    );
}
