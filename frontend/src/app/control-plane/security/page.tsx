/**
 * @file frontend/src/app/control-plane/security/page.tsx
 * @description Security (M11, restyled in F5): the audit trail of the
 * workspace, the integrity of its hash chain, and the provenance of what
 * the tools returned.
 *
 * GET /api/audit returns the latest tool calls recorded by the Tool Gateway
 * (who, which tool, risk, policy decision, outcome) and the Control Plane
 * changes (settings, imported skills), re-verifies the append-only hash
 * chain (a deleted or modified row shows up here) and says for each tool
 * whether its output is untrusted content. The list follows live run
 * events.
 */
"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useMemo, useState } from "react";

import LiveBadge from "@/components/control-plane/LiveBadge";
import type { AuditEntry } from "@/components/control-plane/RunDetailView";
import styles from "@/components/control-plane/control.module.css";
import { getJson } from "@/lib/api/client";
import { useLiveRefresh } from "@/lib/api/events";
import { catalog, localeOf, useLanguage, type Lang } from "@/lib/i18n";
import { ACTION_TEXT, DECISION_TEXT, RISK_LABELS } from "@/lib/nucleo/tools";
import { runHref } from "@/lib/routes";

type AuditRow = AuditEntry & { untrusted_output?: boolean | null };

interface AuditView {
    entries: AuditRow[];
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

const TEXT = catalog({
    en: {
        title: "SECURITY",
        unavailable: "Audit not available:",
        chain: "Audit chain",
        intact: "intact",
        broken: "broken",
        verified: (count: number) => `${count} records verified: none was removed or changed.`,
        brokenAt: (seq: number | null, reason: string | null) =>
            `Broken at record ${seq}: ${reason}. Someone removed or changed a row.`,
        chainHelp:
            "Every tool call and every change from the Control Plane (settings, skills) is written before it happens, linked to the previous one by a hash. No audit record, no action.",
        provenance: "Provenance",
        untrusted: "Untrusted content",
        untrustedHelp:
            "Web pages, files, MCP servers and imported skills are external content: they can hide instructions. After reading one, the run is marked and every high-risk action waits for your approval; the same goes for commands given by voice. Each run's view says whether it read external content and which tools it could use. Which tools return external content is shown in",
        tools: "Tools",
        log: "Log",
        decision: "Decision",
        all: "all",
        tool: "Tool",
        allTools: "all",
        externalOnly: "external content only",
        empty: "No entries in the audit.",
        time: "Time",
        risk: "Risk",
        outcome: "Outcome",
        run: "Run",
        returnsExternal: "returns external content",
        short: { low: "low", medium: "medium", high: "high" } as Record<string, string>,
        writtenBefore: "written before running",
        failed: "failed",
    },
    it: {
        title: "SICUREZZA",
        unavailable: "Audit non disponibile:",
        chain: "Catena dell'audit",
        intact: "integra",
        broken: "rotta",
        verified: (count: number) => `${count} record verificati: nessuno è stato tolto o cambiato.`,
        brokenAt: (seq: number | null, reason: string | null) =>
            `Rotta al record ${seq}: ${reason}. Qualcuno ha tolto o cambiato una riga.`,
        chainHelp:
            "Ogni chiamata a un tool e ogni cambio dal Control Plane (impostazioni, skill) viene scritto prima di avvenire, legato al precedente con un hash. Senza scrittura nell'audit, niente azione.",
        provenance: "Provenienza",
        untrusted: "Contenuti non affidabili",
        untrustedHelp:
            "Pagine web, file, server MCP e skill importate sono contenuto esterno: possono contenere istruzioni nascoste. Dopo averne letto uno, la run è segnata e ogni azione a rischio alto aspetta la tua approvazione; lo stesso vale per i comandi dati a voce. La vista di ogni run dice se ha letto contenuti esterni e quali tool ha potuto usare. Quali tool restituiscono contenuto esterno lo vedi in",
        tools: "Strumenti",
        log: "Registro",
        decision: "Decisione",
        all: "tutte",
        tool: "Tool",
        allTools: "tutti",
        externalOnly: "solo contenuto esterno",
        empty: "Nessuna voce nell'audit.",
        time: "Ora",
        risk: "Rischio",
        outcome: "Esito",
        run: "Run",
        returnsExternal: "restituisce contenuto esterno",
        short: { low: "basso", medium: "medio", high: "alto" } as Record<string, string>,
        writtenBefore: "scritto prima di eseguire",
        failed: "non riuscito",
    },
});

function time(value: string | null, lang: Lang): string {
    if (!value) {
        return "-";
    }
    const date = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
    return Number.isNaN(date.getTime())
        ? value
        : date.toLocaleString(localeOf(lang), { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function SecurityPage() {
    const lang = useLanguage();
    const t = TEXT[lang];
    const [view, setView] = useState<AuditView | null>(null);
    const [decision, setDecision] = useState<(typeof DECISIONS)[number]>("");
    const [tool, setTool] = useState("");
    const [externalOnly, setExternalOnly] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        const params: Record<string, string | number> = { limit: 200 };
        if (decision) {
            params.decision = decision;
        }
        if (tool) {
            params.tool = tool;
        }
        try {
            setView(await getJson<AuditView>("/api/audit", { params }));
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        }
    }, [decision, tool]);

    const live = useLiveRefresh(refresh, ["run.state", "run.resumed", "approval.decided"]);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    // The tool filter offers what the unfiltered list has shown so far.
    const [seenTools, setSeenTools] = useState<string[]>([]);
    useEffect(() => {
        if (view) {
            const update = setTimeout(
                () =>
                    setSeenTools((current) =>
                        [...new Set([...current, ...view.entries.map((entry) => entry.tool_name)])].sort(),
                    ),
                0,
            );
            return () => clearTimeout(update);
        }
    }, [view]);

    const entries = useMemo(
        () => (view?.entries ?? []).filter((entry) => !externalOnly || entry.untrusted_output === true),
        [view, externalOnly],
    );
    const chain = view?.chain;

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>{t.title}</h1>
                <LiveBadge state={live} />
            </div>

            {error && (
                <p className={styles.error}>
                    {t.unavailable} {error}
                </p>
            )}

            {chain && (
                <section className={`${styles.card} ${chain.valid ? "" : styles.amber}`} aria-label={t.chain}>
                    <h2 className={styles.h2}>{t.chain}</h2>
                    <p role="status" className={styles.row}>
                        <span className={styles.badge} data-tone={chain.valid ? "ok" : "bad"}>
                            {chain.valid ? t.intact : t.broken}
                        </span>
                        <span className={chain.valid ? styles.muted : styles.error}>
                            {chain.valid ? t.verified(chain.checked) : t.brokenAt(chain.broken_at_seq, chain.reason)}
                        </span>
                    </p>
                    <p className={styles.help}>{t.chainHelp}</p>
                </section>
            )}

            <section className={styles.card} aria-label={t.provenance}>
                <h2 className={styles.h2}>{t.untrusted}</h2>
                <p className={styles.help}>
                    {t.untrustedHelp}{" "}
                    <Link href="/control-plane/tools" className={styles.link}>
                        {t.tools}
                    </Link>
                    .
                </p>
            </section>

            <section className={styles.section} aria-label={t.log}>
                <h2 className={styles.h2}>
                    {t.log} <span>{entries.length}</span>
                </h2>
                <div className={styles.filters}>
                    <label className={styles.field}>
                        {t.decision}
                        <select
                            value={decision}
                            onChange={(event) => setDecision(event.target.value as (typeof DECISIONS)[number])}
                        >
                            {DECISIONS.map((item) => (
                                <option key={item} value={item}>
                                    {item ? (DECISION_TEXT[lang][item]?.label ?? item) : t.all}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className={styles.field}>
                        {t.tool}
                        <select value={tool} onChange={(event) => setTool(event.target.value)}>
                            <option value="">{t.allTools}</option>
                            {[...new Set([...seenTools, ...(tool ? [tool] : [])])].map((name) => (
                                <option key={name} value={name}>
                                    {ACTION_TEXT[lang][name] ?? name}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className={styles.check}>
                        <input
                            type="checkbox"
                            checked={externalOnly}
                            onChange={(event) => setExternalOnly(event.target.checked)}
                        />
                        {t.externalOnly}
                    </label>
                </div>

                {view && entries.length === 0 ? (
                    <p className={styles.muted}>{t.empty}</p>
                ) : (
                    <div className={styles.tableWrap}>
                        <table className={styles.table}>
                            <thead>
                                <tr>
                                    <th>{t.time}</th>
                                    <th>{t.tool}</th>
                                    <th>{t.risk}</th>
                                    <th>{t.decision}</th>
                                    <th>{t.outcome}</th>
                                    <th>{t.run}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {entries.map((entry) => {
                                    const level = entry.risk?.toLowerCase() ?? "";
                                    const risk = RISK_LABELS[lang][level as keyof (typeof RISK_LABELS)[Lang]];
                                    const verdict = entry.decision ? DECISION_TEXT[lang][entry.decision] : undefined;
                                    return (
                                        <tr key={entry.id}>
                                            <td className={styles.num}>{time(entry.timestamp, lang)}</td>
                                            <td>
                                                <span className={styles.mono}>{ACTION_TEXT[lang][entry.tool_name] ?? entry.tool_name}</span>
                                                {entry.untrusted_output && (
                                                    <span className={styles.sub}>{t.returnsExternal}</span>
                                                )}
                                            </td>
                                            <td>
                                                {risk ? (
                                                    <span className={styles.badge} data-tone={risk.tone}>
                                                        {t.short[level] ?? level}
                                                    </span>
                                                ) : (
                                                    entry.risk
                                                )}
                                            </td>
                                            <td>
                                                <span className={styles.badge} data-tone={verdict?.tone}>
                                                    {verdict?.label ?? entry.decision ?? "-"}
                                                </span>
                                            </td>
                                            <td className={`${styles.task} ${styles.outcome}`}>
                                                {entry.success ? (
                                                    <span className={styles.muted}>ok</span>
                                                ) : entry.decision === "EXECUTING" ? (
                                                    <span className={styles.muted}>{t.writtenBefore}</span>
                                                ) : (
                                                    <span className={styles.error}>{entry.error ?? t.failed}</span>
                                                )}
                                            </td>
                                            <td className={styles.mono}>
                                                {entry.run_id ? (
                                                    <Link href={runHref(entry.run_id)} className={styles.link}>
                                                        {entry.run_id.slice(0, 16)}
                                                    </Link>
                                                ) : (
                                                    <span className={styles.faint}>Control Plane</span>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </section>
        </main>
    );
}
