/**
 * @file frontend/src/app/control-plane/tools/page.tsx
 * @description Strumenti (F5, ADR-026): every skill with its tools and the
 * risk of each, switching tools on and off, the skill index, the folders,
 * hosts and MCP servers the tools may reach, what each MCP server answered
 * and the risk of its tools (ADR-033), and the sandbox.
 *
 * Reads GET /api/tools; every change is a setting saved through
 * PUT /api/settings (validated, audited, applied to the next run without a
 * restart): AEHUB_DISABLED_TOOLS, AEHUB_TOOL_SELECTION, AEHUB_TOOL_TOP_K,
 * AEHUB_MCP_ALLOWED_SERVERS, AEHUB_MCP_TOOL_RISK. POST /api/tools/mcp/refresh
 * connects to the MCP servers again. Folders and API hosts are startup
 * parameters, shown read only.
 */
"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import { getJson, postJson } from "@/lib/api/client";
import { useSettings, type SettingChanges } from "@/lib/api/settings";
import {
    disabledValue,
    riskValue,
    serversValue,
    validServer,
    type McpServerStatus,
    type Risk,
    type SkillGroup,
    type ToolInfo,
    type ToolsView,
} from "@/lib/api/tools";
import { RISK_LABELS, SKILL_TEXT, SOURCE_TEXT, TOOL_TEXT, skillTitle } from "@/lib/nucleo/tools";

function message(err: unknown): string {
    return err instanceof Error ? err.message : String(err);
}

const RISK_CHOICES: { value: Risk; label: string }[] = [
    { value: "high", label: "alto: chiede sempre" },
    { value: "medium", label: "medio" },
    { value: "low", label: "basso" },
];

const MCP_STATE: Record<McpServerStatus["state"], { label: string; tone: "ok" | "warn" | "bad" }> =
    {
        connected: { label: "collegato", tone: "ok" },
        error: { label: "non risponde", tone: "bad" },
        waiting: { label: "non ancora controllato", tone: "warn" },
    };

function ToolRow({
    tool,
    busy,
    onToggle,
    onRisk,
}: {
    tool: ToolInfo;
    busy: boolean;
    onToggle: (tool: ToolInfo, enabled: boolean) => void;
    /** Only MCP tools: their risk is the owner's to set. */
    onRisk?: (tool: ToolInfo, risk: Risk) => void;
}) {
    const risk = RISK_LABELS[tool.risk] ?? RISK_LABELS.medium;

    return (
        <li className={styles.tool} data-enabled={tool.enabled}>
            <label className={styles.switch}>
                <input
                    type="checkbox"
                    role="switch"
                    checked={tool.enabled}
                    disabled={busy}
                    onChange={(event) => onToggle(tool, event.target.checked)}
                    aria-label={`${tool.name} ${tool.enabled ? "attivo" : "spento"}`}
                />
                <span aria-hidden="true" />
            </label>
            <div className={styles.toolBody}>
                <span className={styles.toolName}>{tool.name}</span>
                <span className={styles.help}>{TOOL_TEXT[tool.name] ?? tool.description}</span>
                <span className={styles.row}>
                    <span className={styles.badge} data-tone={risk.tone}>
                        {risk.label}
                    </span>
                    {tool.requires_approval && (
                        <span className={styles.badge} data-tone="warn">
                            chiede sempre approvazione
                        </span>
                    )}
                    {tool.network && <span className={styles.badge}>rete</span>}
                    {tool.filesystem && <span className={styles.badge}>file</span>}
                    {tool.modifies_files && <span className={styles.badge}>modifica file</span>}
                    {tool.untrusted_output && (
                        <span className={styles.badge} data-tone="live">
                            contenuto esterno
                        </span>
                    )}
                </span>
                {onRisk && (
                    <label className={styles.field}>
                        Rischio
                        <select
                            value={tool.risk}
                            disabled={busy}
                            aria-label={`Rischio di ${tool.name}`}
                            onChange={(event) => onRisk(tool, event.target.value as Risk)}
                        >
                            {RISK_CHOICES.map((choice) => (
                                <option key={choice.value} value={choice.value}>
                                    {choice.label}
                                </option>
                            ))}
                        </select>
                    </label>
                )}
            </div>
        </li>
    );
}

function SkillCard({
    skill,
    busy,
    onToggle,
    onRisk,
}: {
    skill: SkillGroup;
    busy: boolean;
    onToggle: (tool: ToolInfo, enabled: boolean) => void;
    onRisk: (tool: ToolInfo, risk: Risk) => void;
}) {
    const mcp = skill.source === "mcp";

    return (
        <section className={styles.card} aria-label={skillTitle(skill.name)}>
            <div className={styles.settingHead}>
                <h3 className={styles.settingLabel}>{skillTitle(skill.name)}</h3>
                <span className={styles.source}>
                    {SOURCE_TEXT[skill.source]} · {skill.name}
                </span>
            </div>
            <p className={styles.help}>
                {SKILL_TEXT[skill.name]?.description ?? skill.description}
            </p>
            {skill.tools.length ? (
                <ul className={styles.plain}>
                    {skill.tools.map((tool) => (
                        <ToolRow
                            key={tool.name}
                            tool={tool}
                            busy={busy}
                            onToggle={onToggle}
                            onRisk={mcp ? onRisk : undefined}
                        />
                    ))}
                </ul>
            ) : (
                <p className={styles.muted}>
                    {skill.source === "imported" ? (
                        <>
                            Nessuna skill accesa:{" "}
                            <Link href="/control-plane/skills" className={styles.link}>
                                importale e accendile
                            </Link>
                            .
                        </>
                    ) : mcp ? (
                        "Nessun server MCP collegato: aggiungilo in Confini, poi Ricollega."
                    ) : (
                        "Nessun tool in questo momento."
                    )}
                </p>
            )}
        </section>
    );
}

export default function ToolsPage() {
    const { save } = useSettings();
    const [view, setView] = useState<ToolsView | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [note, setNote] = useState<string | null>(null);
    const [selection, setSelection] = useState<{ enabled: boolean; topK: string } | null>(null);
    const [servers, setServers] = useState<string[]>([]);

    const refresh = useCallback(async () => {
        try {
            const next = await getJson<ToolsView>("/api/tools");
            setView(next);
            setSelection({ enabled: next.selection.enabled, topK: String(next.selection.top_k) });
            setServers(next.boundaries.mcp_servers.length ? next.boundaries.mcp_servers : [""]);
            setError(null);
        } catch (err) {
            setError(message(err));
        }
    }, []);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    const apply = async (changes: SettingChanges, done: string) => {
        setBusy(true);
        setNote(null);
        const outcome = await save(changes);
        setBusy(false);
        if (outcome.ok) {
            setNote(done);
            await refresh();
        } else {
            const details = Object.values(outcome.errors).join(" ");
            setNote(`${outcome.message ?? "Non salvato."} ${details}`.trim());
        }
    };

    if (error) {
        return (
            <main className={styles.page}>
                <p className={styles.error}>Strumenti non disponibili: {error}</p>
            </main>
        );
    }

    if (!view || !selection) {
        return (
            <main className={styles.page}>
                <p className={styles.muted}>Carico gli strumenti…</p>
            </main>
        );
    }

    const tools = view.skills.flatMap((skill) => skill.tools);
    const active = tools.filter((tool) => tool.enabled).length;
    const known = new Set(tools.map((tool) => tool.name));
    const stale = view.disabled.filter((name) => !known.has(name));
    const topK = Number(selection.topK);
    const selectionDirty =
        selection.enabled !== view.selection.enabled ||
        selection.topK !== String(view.selection.top_k);
    const topKValid = Number.isInteger(topK) && topK >= 1 && topK <= 50;
    const serversDirty = serversValue(servers) !== serversValue(view.boundaries.mcp_servers);
    const serversValid = servers.every((row) => !row.trim() || validServer(row));

    const setRisk = (tool: ToolInfo, risk: Risk) =>
        apply(
            { AEHUB_MCP_TOOL_RISK: riskValue(view.mcp.risk, tool.name, risk) },
            risk === "high"
                ? `${tool.name} chiede di nuovo l'approvazione a ogni chiamata.`
                : `${tool.name} ora è a rischio ${risk === "low" ? "basso" : "medio"}: non chiede più l'approvazione.`
        );

    const reconnect = async () => {
        setBusy(true);
        setNote(null);
        try {
            await postJson("/api/tools/mcp/refresh", {});
            setNote("Server MCP ricontrollati.");
            await refresh();
        } catch (err) {
            setNote(`Ricollegamento non riuscito: ${message(err)}`);
        } finally {
            setBusy(false);
        }
    };

    const toggle = (tool: ToolInfo, enabled: boolean) =>
        apply(
            { AEHUB_DISABLED_TOOLS: disabledValue(view.disabled, tool.name, enabled) },
            enabled
                ? `${tool.name} è attivo dalla prossima run.`
                : `${tool.name} è spento dalla prossima run.`
        );

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>STRUMENTI</h1>
                <span className={styles.badge} data-tone="ok">
                    {active} tool attivi su {tools.length}
                </span>
                {note && (
                    <span className={styles.muted} role="status">
                        {note}
                    </span>
                )}
            </div>

            <p className={styles.muted}>
                Ogni chiamata passa dal Tool Gateway: policy, approvazioni, provenienza, audit e
                budget. Un tool spento non viene mostrato all&apos;agente e, se lo chiede lo stesso,
                la chiamata è rifiutata. Dopo un contenuto esterno ogni azione a rischio alto
                aspetta la tua approvazione.
            </p>

            <section className={styles.card} aria-label="Indice delle skill">
                <h2 className={styles.h2}>Indice delle skill</h2>
                <p className={styles.help}>
                    Prima di ogni run l&apos;indice sceglie dal testo del compito i tool che
                    servono: l&apos;agente vede solo quelli, e un&apos;istruzione nascosta in una
                    pagina non può chiamarne altri.
                </p>
                <div className={styles.filters}>
                    <div className={styles.row} role="radiogroup" aria-label="Indice delle skill">
                        <label className={styles.check}>
                            <input
                                type="radio"
                                name="selection"
                                checked={selection.enabled}
                                onChange={() => setSelection({ ...selection, enabled: true })}
                            />
                            acceso
                        </label>
                        <label className={styles.check}>
                            <input
                                type="radio"
                                name="selection"
                                checked={!selection.enabled}
                                onChange={() => setSelection({ ...selection, enabled: false })}
                            />
                            spento
                        </label>
                    </div>
                    <label className={styles.field}>
                        Tool per run
                        <input
                            type="number"
                            min={1}
                            max={50}
                            className={styles.narrow}
                            value={selection.topK}
                            aria-invalid={!topKValid}
                            onChange={(event) =>
                                setSelection({ ...selection, topK: event.target.value })
                            }
                        />
                    </label>
                    <button
                        type="button"
                        className={`${styles.btn} ${styles.go}`}
                        disabled={busy || !selectionDirty || !topKValid}
                        onClick={() =>
                            apply(
                                {
                                    AEHUB_TOOL_SELECTION: selection.enabled ? "on" : "off",
                                    AEHUB_TOOL_TOP_K: String(topK),
                                },
                                "Indice salvato: vale dalla prossima run."
                            )
                        }
                    >
                        Salva
                    </button>
                </div>
                <p className={styles.muted}>
                    {!view.selection.enabled
                        ? "Spento: ogni run vede tutti i tool attivi."
                        : view.selection.active
                          ? `Ogni run vede al massimo ${view.selection.top_k} tool su ${view.selection.tools}. Quali ha scelto lo trovi nella vista della run.`
                          : `I tool attivi sono ${view.selection.tools}, non più di ${view.selection.top_k}: ogni run li vede tutti.`}
                </p>
            </section>

            <section className={styles.section} aria-label="Catalogo">
                <h2 className={styles.h2}>
                    Catalogo <span>{view.skills.length} skill</span>
                </h2>
                <div className={styles.grid}>
                    {view.skills.map((skill) => (
                        <SkillCard
                            key={skill.name}
                            skill={skill}
                            busy={busy}
                            onToggle={toggle}
                            onRisk={setRisk}
                        />
                    ))}
                </div>
                {stale.length > 0 && (
                    <div className={styles.issue} data-tone="warn">
                        <span>
                            Spenti ma non più presenti:{" "}
                            <span className={styles.mono}>{stale.join(", ")}</span>
                        </span>
                        <button
                            type="button"
                            className={styles.linkBtn}
                            disabled={busy}
                            onClick={() =>
                                apply(
                                    {
                                        AEHUB_DISABLED_TOOLS:
                                            view.disabled
                                                .filter((name) => known.has(name))
                                                .join(",") || null,
                                    },
                                    "Elenco ripulito."
                                )
                            }
                        >
                            Togli dall&apos;elenco
                        </button>
                    </div>
                )}
            </section>

            <section className={styles.card} aria-label="Confini">
                <h2 className={styles.h2}>Confini</h2>

                <div className={styles.setting}>
                    <span className={styles.settingLabel}>Cartelle dei tool</span>
                    <p className={styles.help}>
                        I tool che leggono o scrivono file restano qui dentro. Si scelgono
                        all&apos;avvio, dal launcher o da{" "}
                        <code className={styles.mono}>AEHUB_ALLOWED_DIRS</code>.
                    </p>
                    <ul className={styles.lines}>
                        {view.boundaries.directories.map((folder) => (
                            <li key={folder.path}>
                                <span className={styles.mono}>{folder.path}</span>
                                <b>{folder.exists ? "esiste" : "non esiste ancora"}</b>
                            </li>
                        ))}
                    </ul>
                </div>

                <div className={styles.setting}>
                    <span className={styles.settingLabel}>Host dell&apos;API</span>
                    <p className={styles.help}>
                        L&apos;API risponde solo a questi nomi, contro il DNS rebinding. Si
                        aggiungono all&apos;avvio con{" "}
                        <code className={styles.mono}>AEHUB_ALLOWED_HOSTS</code>.
                    </p>
                    <p className={styles.mono}>{view.boundaries.api_hosts.join(" · ")}</p>
                </div>

                <div className={styles.setting}>
                    <span className={styles.settingLabel}>Server MCP consentiti</span>
                    <p className={styles.help}>
                        Il client MCP si collega solo a questi indirizzi (https, o http solo verso
                        questo computer); vuoto vuol dire nessuno. Quello che un server MCP
                        restituisce conta sempre come contenuto esterno, e ogni suo tool chiede la
                        tua approvazione finché non ne abbassi il rischio nel catalogo.
                    </p>
                    <ul className={styles.servers}>
                        {servers.map((row, index) => (
                            <li key={index} data-invalid={Boolean(row.trim()) && !validServer(row)}>
                                <input
                                    className={styles.input}
                                    value={row}
                                    placeholder="https://server-mcp.example/sse"
                                    aria-label={`Server MCP ${index + 1}`}
                                    spellCheck={false}
                                    onChange={(event) =>
                                        setServers(
                                            servers.map((item, at) =>
                                                at === index ? event.target.value : item
                                            )
                                        )
                                    }
                                />
                                <span className={styles.icons}>
                                    <button
                                        type="button"
                                        className={styles.icon}
                                        aria-label={`Togli il server ${index + 1}`}
                                        onClick={() => {
                                            const next = servers.filter((_, at) => at !== index);
                                            setServers(next.length ? next : [""]);
                                        }}
                                    >
                                        ×
                                    </button>
                                </span>
                            </li>
                        ))}
                    </ul>
                    <div className={styles.row}>
                        <button
                            type="button"
                            className={styles.linkBtn}
                            onClick={() => setServers([...servers, ""])}
                        >
                            + aggiungi un server
                        </button>
                        <button
                            type="button"
                            className={`${styles.btn} ${styles.go}`}
                            disabled={busy || !serversDirty || !serversValid}
                            onClick={() =>
                                apply(
                                    { AEHUB_MCP_ALLOWED_SERVERS: serversValue(servers) },
                                    "Server MCP salvati."
                                )
                            }
                        >
                            Salva i server
                        </button>
                        {!serversValid && (
                            <span className={styles.error} role="alert">
                                Un indirizzo http(s) per riga, senza credenziali.
                            </span>
                        )}
                    </div>
                </div>

                <div className={styles.setting}>
                    <span className={styles.settingLabel}>Server MCP</span>
                    <p className={styles.help}>
                        Un server che chiede un login vuole un token: va nel keyring come{" "}
                        <code className={styles.mono}>AEHUB_MCP_TOKENS</code> (
                        <code className={styles.mono}>host=token</code>, separati da virgole) con{" "}
                        <code className={styles.mono}>python scripts/aehub.py setup</code>. Il token
                        va solo al suo host. Dopo un token nuovo, ricollega.
                    </p>
                    {view.mcp.servers.length ? (
                        <ul className={styles.lines} aria-label="Stato dei server MCP">
                            {view.mcp.servers.map((server) => {
                                const state = MCP_STATE[server.state] ?? MCP_STATE.waiting;
                                return (
                                    <li key={server.url}>
                                        <span>
                                            <span className={styles.mono}>{server.name}</span> ·{" "}
                                            {server.url}
                                            {server.error && (
                                                <span className={styles.help}>
                                                    {" "}
                                                    · {server.error}
                                                </span>
                                            )}
                                        </span>
                                        <span className={styles.row}>
                                            <span className={styles.badge} data-tone={state.tone}>
                                                {server.state === "connected"
                                                    ? `${state.label} · ${server.tools.length} tool`
                                                    : state.label}
                                            </span>
                                            <span className={styles.badge}>
                                                {server.token ? "token nel keyring" : "senza token"}
                                            </span>
                                        </span>
                                    </li>
                                );
                            })}
                        </ul>
                    ) : (
                        <p className={styles.muted}>Nessun server consentito.</p>
                    )}
                    <div className={styles.row}>
                        <button
                            type="button"
                            className={styles.btn}
                            disabled={busy || !view.mcp.servers.length}
                            onClick={reconnect}
                        >
                            Ricollega
                        </button>
                    </div>
                </div>
            </section>

            <section className={styles.card} aria-label="Sandbox Docker">
                <h2 className={styles.h2}>Sandbox Docker</h2>
                <dl className={styles.facts}>
                    <dt>Docker</dt>
                    <dd>
                        <span
                            className={styles.badge}
                            data-tone={view.sandbox.docker ? "ok" : "warn"}
                        >
                            {view.sandbox.docker
                                ? "disponibile"
                                : "non trovato: Python e shell non possono girare"}
                        </span>
                    </dd>
                    <dt>Immagine</dt>
                    <dd className={styles.mono}>{view.sandbox.image}</dd>
                    <dt>Memoria</dt>
                    <dd className={styles.mono}>{view.sandbox.memory_limit}</dd>
                    <dt>Rete</dt>
                    <dd>
                        {view.sandbox.network ? "accesa" : "spenta: il codice non esce su internet"}
                    </dd>
                </dl>
            </section>
        </main>
    );
}
