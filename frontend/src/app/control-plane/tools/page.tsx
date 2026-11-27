/**
 * @file frontend/src/app/control-plane/tools/page.tsx
 * @description Tools (F5, ADR-026): every skill with its tools and the risk
 * of each, switching tools on and off, the skill index, the folders, hosts
 * and MCP servers the tools may reach, what each MCP server answered and the
 * risk of its tools (ADR-033), and the sandbox.
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
import TrashCard from "@/components/control-plane/TrashCard";
import { getJson, postJson } from "@/lib/api/client";
import { useSettings, type SettingChanges } from "@/lib/api/settings";
import {
    absolutePath,
    agentFolders,
    disabledValue,
    foldersValue,
    riskValue,
    serversValue,
    validServer,
    type McpServerStatus,
    type Risk,
    type SkillGroup,
    type ToolInfo,
    type ToolsView,
} from "@/lib/api/tools";
import { catalog, useLanguage, useText } from "@/lib/i18n";
import { RISK_LABELS, SKILL_TEXT, SOURCE_TEXT, TOOL_TEXT, skillTitle } from "@/lib/nucleo/tools";

function message(err: unknown): string {
    return err instanceof Error ? err.message : String(err);
}

type Tone = "ok" | "warn" | "bad";

const MCP_TONES: Record<McpServerStatus["state"], Tone> = { connected: "ok", error: "bad", waiting: "warn" };

const TEXT = catalog({
    en: {
        riskChoices: { high: "high: always asks", medium: "medium", low: "low" } as Record<Risk, string>,
        mcpStates: {
            connected: "connected",
            error: "not answering",
            waiting: "not checked yet",
        } as Record<McpServerStatus["state"], string>,
        toolState: (name: string, enabled: boolean) => `${name} ${enabled ? "on" : "off"}`,
        alwaysAsks: "always asks for approval",
        network: "network",
        file: "file",
        modifiesFiles: "modifies files",
        external: "external content",
        risk: "Risk",
        riskOf: (name: string) => `Risk of ${name}`,
        noSkill: "No skill is on:",
        importThem: "import and turn them on",
        noMcp: "No MCP server connected: add one under Boundaries, then Reconnect.",
        noTools: "No tools at the moment.",
        notSaved: "Not saved.",
        unavailable: "Tools not available:",
        loading: "Loading the tools…",
        riskHigh: (name: string) => `${name} asks for approval on every call again.`,
        riskLowered: (name: string, risk: Risk) =>
            `${name} is now ${risk === "low" ? "low" : "medium"} risk: it no longer asks for approval.`,
        reconnected: "MCP servers checked again.",
        reconnectFailed: "Reconnecting failed:",
        toolOn: (name: string) => `${name} is on from the next run.`,
        toolOff: (name: string) => `${name} is off from the next run.`,
        title: "TOOLS",
        active: (active: number, total: number) => `${active} of ${total} tools on`,
        gateway:
            "Every call goes through the Tool Gateway: policy, approvals, provenance, audit and budget. A tool that is off is not shown to the agent and, if it asks for it anyway, the call is refused. After external content every high-risk action waits for your approval.",
        index: "Skill index",
        indexHelp:
            "Before each run the index picks from the task's text the tools it needs: the agent sees only those, and an instruction hidden in a page cannot call others.",
        on: "on",
        off: "off",
        perRun: "Tools per run",
        save: "Save",
        indexSaved: "Index saved: it applies from the next run.",
        indexOff: "Off: every run sees all the tools that are on.",
        indexActive: (topK: number, tools: number) =>
            `Each run sees at most ${topK} of ${tools} tools. Which ones it chose is in the run's view.`,
        indexAll: (tools: number, topK: number) =>
            `${tools} tools are on, no more than ${topK}: every run sees them all.`,
        catalog: "Catalog",
        skills: (count: number) => `${count} skills`,
        stale: "Off but no longer present:",
        cleaned: "List cleaned.",
        removeFromList: "Remove from the list",
        boundaries: "Boundaries",
        folders: "Folders of the agents",
        foldersHelp: "The working folder is chosen at start, by the launcher or with",
        agentFoldersHelp:
            "Add the folders the agents may use: list, find, read and write files there. Replacing or deleting a file always waits for your approval. ÆHub's own files, hidden files (.ssh, .env…) and AppData stay out of reach.",
        working: "working folder",
        folderN: (index: number) => `Agent folder ${index}`,
        removeFolder: (index: number) => `Remove folder ${index}`,
        addFolder: "+ add a folder",
        saveFolders: "Save the folders",
        foldersSaved: "Folders saved: the agents use them from the next call.",
        folderInvalid: "Write the full path of each folder.",
        exists: "exists",
        notYet: "does not exist yet",
        hosts: "API hosts",
        hostsHelp: "The API answers only to these names, against DNS rebinding. More are added at start with",
        allowedServers: "Allowed MCP servers",
        serversHelp:
            "The MCP client connects only to these addresses (https, or http only to this computer); empty means none. What an MCP server returns always counts as external content, and each of its tools asks for your approval until you lower its risk in the catalog.",
        serverN: (index: number) => `MCP server ${index}`,
        removeServer: (index: number) => `Remove server ${index}`,
        addServer: "+ add a server",
        serversSaved: "MCP servers saved.",
        saveServers: "Save the servers",
        serverInvalid: "One http(s) address per line, without credentials.",
        mcpServers: "MCP servers",
        tokenHelpStart: "A server that asks for a login needs a token: it goes in the keyring as",
        tokenHelpMid: "comma-separated) with",
        tokenHelpEnd: "The token goes only to its host. After a new token, reconnect.",
        serverStates: "State of the MCP servers",
        connectedTools: (label: string, count: number) => `${label} · ${count} tools`,
        tokenSet: "token in the keyring",
        noToken: "no token",
        noServers: "No server allowed.",
        reconnect: "Reconnect",
        sandbox: "Docker sandbox",
        dockerOk: "available",
        dockerMissing: "not found: Python and shell cannot run",
        image: "Image",
        memory: "Memory",
        net: "Network",
        netOn: "on",
        netOff: "off: the code does not reach the internet",
    },
    it: {
        riskChoices: { high: "alto: chiede sempre", medium: "medio", low: "basso" } as Record<Risk, string>,
        mcpStates: {
            connected: "collegato",
            error: "non risponde",
            waiting: "non ancora controllato",
        } as Record<McpServerStatus["state"], string>,
        toolState: (name: string, enabled: boolean) => `${name} ${enabled ? "attivo" : "spento"}`,
        alwaysAsks: "chiede sempre approvazione",
        network: "rete",
        file: "file",
        modifiesFiles: "modifica file",
        external: "contenuto esterno",
        risk: "Rischio",
        riskOf: (name: string) => `Rischio di ${name}`,
        noSkill: "Nessuna skill accesa:",
        importThem: "importale e accendile",
        noMcp: "Nessun server MCP collegato: aggiungilo in Confini, poi Ricollega.",
        noTools: "Nessun tool in questo momento.",
        notSaved: "Non salvato.",
        unavailable: "Strumenti non disponibili:",
        loading: "Carico gli strumenti…",
        riskHigh: (name: string) => `${name} chiede di nuovo l'approvazione a ogni chiamata.`,
        riskLowered: (name: string, risk: Risk) =>
            `${name} ora è a rischio ${risk === "low" ? "basso" : "medio"}: non chiede più l'approvazione.`,
        reconnected: "Server MCP ricontrollati.",
        reconnectFailed: "Ricollegamento non riuscito:",
        toolOn: (name: string) => `${name} è attivo dalla prossima run.`,
        toolOff: (name: string) => `${name} è spento dalla prossima run.`,
        title: "STRUMENTI",
        active: (active: number, total: number) => `${active} tool attivi su ${total}`,
        gateway:
            "Ogni chiamata passa dal Tool Gateway: policy, approvazioni, provenienza, audit e budget. Un tool spento non viene mostrato all'agente e, se lo chiede lo stesso, la chiamata è rifiutata. Dopo un contenuto esterno ogni azione a rischio alto aspetta la tua approvazione.",
        index: "Indice delle skill",
        indexHelp:
            "Prima di ogni run l'indice sceglie dal testo del compito i tool che servono: l'agente vede solo quelli, e un'istruzione nascosta in una pagina non può chiamarne altri.",
        on: "acceso",
        off: "spento",
        perRun: "Tool per run",
        save: "Salva",
        indexSaved: "Indice salvato: vale dalla prossima run.",
        indexOff: "Spento: ogni run vede tutti i tool attivi.",
        indexActive: (topK: number, tools: number) =>
            `Ogni run vede al massimo ${topK} tool su ${tools}. Quali ha scelto lo trovi nella vista della run.`,
        indexAll: (tools: number, topK: number) =>
            `I tool attivi sono ${tools}, non più di ${topK}: ogni run li vede tutti.`,
        catalog: "Catalogo",
        skills: (count: number) => `${count} skill`,
        stale: "Spenti ma non più presenti:",
        cleaned: "Elenco ripulito.",
        removeFromList: "Togli dall'elenco",
        boundaries: "Confini",
        folders: "Cartelle degli agenti",
        foldersHelp: "La cartella di lavoro si sceglie all'avvio, dal launcher o da",
        agentFoldersHelp:
            "Aggiungi le cartelle che gli agenti possono usare: elencare, cercare, leggere e scrivere file lì dentro. Sostituire o eliminare un file aspetta sempre la tua approvazione. I file di ÆHub, i file nascosti (.ssh, .env…) e AppData restano fuori portata.",
        working: "cartella di lavoro",
        folderN: (index: number) => `Cartella degli agenti ${index}`,
        removeFolder: (index: number) => `Togli la cartella ${index}`,
        addFolder: "+ aggiungi una cartella",
        saveFolders: "Salva le cartelle",
        foldersSaved: "Cartelle salvate: gli agenti le usano dalla prossima chiamata.",
        folderInvalid: "Scrivi il percorso completo di ogni cartella.",
        exists: "esiste",
        notYet: "non esiste ancora",
        hosts: "Host dell'API",
        hostsHelp: "L'API risponde solo a questi nomi, contro il DNS rebinding. Si aggiungono all'avvio con",
        allowedServers: "Server MCP consentiti",
        serversHelp:
            "Il client MCP si collega solo a questi indirizzi (https, o http solo verso questo computer); vuoto vuol dire nessuno. Quello che un server MCP restituisce conta sempre come contenuto esterno, e ogni suo tool chiede la tua approvazione finché non ne abbassi il rischio nel catalogo.",
        serverN: (index: number) => `Server MCP ${index}`,
        removeServer: (index: number) => `Togli il server ${index}`,
        addServer: "+ aggiungi un server",
        serversSaved: "Server MCP salvati.",
        saveServers: "Salva i server",
        serverInvalid: "Un indirizzo http(s) per riga, senza credenziali.",
        mcpServers: "Server MCP",
        tokenHelpStart: "Un server che chiede un login vuole un token: va nel keyring come",
        tokenHelpMid: "separati da virgole) con",
        tokenHelpEnd: "Il token va solo al suo host. Dopo un token nuovo, ricollega.",
        serverStates: "Stato dei server MCP",
        connectedTools: (label: string, count: number) => `${label} · ${count} tool`,
        tokenSet: "token nel keyring",
        noToken: "senza token",
        noServers: "Nessun server consentito.",
        reconnect: "Ricollega",
        sandbox: "Sandbox Docker",
        dockerOk: "disponibile",
        dockerMissing: "non trovato: Python e shell non possono girare",
        image: "Immagine",
        memory: "Memoria",
        net: "Rete",
        netOn: "accesa",
        netOff: "spenta: il codice non esce su internet",
    },
});

const RISKS: Risk[] = ["high", "medium", "low"];

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
    const lang = useLanguage();
    const t = TEXT[lang];
    const risk = RISK_LABELS[lang][tool.risk] ?? RISK_LABELS[lang].medium;

    return (
        <li className={styles.tool} data-enabled={tool.enabled}>
            <label className={styles.switch}>
                <input
                    type="checkbox"
                    role="switch"
                    checked={tool.enabled}
                    disabled={busy}
                    onChange={(event) => onToggle(tool, event.target.checked)}
                    aria-label={t.toolState(tool.name, tool.enabled)}
                />
                <span aria-hidden="true" />
            </label>
            <div className={styles.toolBody}>
                <span className={styles.toolName}>{tool.name}</span>
                <span className={styles.help}>{TOOL_TEXT[lang][tool.name] ?? tool.description}</span>
                <span className={styles.row}>
                    <span className={styles.badge} data-tone={risk.tone}>
                        {risk.label}
                    </span>
                    {tool.requires_approval && (
                        <span className={styles.badge} data-tone="warn">
                            {t.alwaysAsks}
                        </span>
                    )}
                    {tool.network && <span className={styles.badge}>{t.network}</span>}
                    {tool.filesystem && <span className={styles.badge}>{t.file}</span>}
                    {tool.modifies_files && <span className={styles.badge}>{t.modifiesFiles}</span>}
                    {tool.untrusted_output && (
                        <span className={styles.badge} data-tone="live">
                            {t.external}
                        </span>
                    )}
                </span>
                {onRisk && (
                    <label className={styles.field}>
                        {t.risk}
                        <select
                            value={tool.risk}
                            disabled={busy}
                            aria-label={t.riskOf(tool.name)}
                            onChange={(event) => onRisk(tool, event.target.value as Risk)}
                        >
                            {RISKS.map((value) => (
                                <option key={value} value={value}>
                                    {t.riskChoices[value]}
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
    const lang = useLanguage();
    const t = TEXT[lang];
    const mcp = skill.source === "mcp";
    const title = skillTitle(skill.name, lang);

    return (
        <section className={styles.card} aria-label={title}>
            <div className={styles.settingHead}>
                <h3 className={styles.settingLabel}>{title}</h3>
                <span className={styles.source}>
                    {SOURCE_TEXT[lang][skill.source]} · {skill.name}
                </span>
            </div>
            <p className={styles.help}>{SKILL_TEXT[lang][skill.name]?.description ?? skill.description}</p>
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
                            {t.noSkill}{" "}
                            <Link href="/control-plane/skills" className={styles.link}>
                                {t.importThem}
                            </Link>
                            .
                        </>
                    ) : mcp ? (
                        t.noMcp
                    ) : (
                        t.noTools
                    )}
                </p>
            )}
        </section>
    );
}

export default function ToolsPage() {
    const t = useText(TEXT);
    const { save } = useSettings();
    const [view, setView] = useState<ToolsView | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [note, setNote] = useState<string | null>(null);
    const [selection, setSelection] = useState<{ enabled: boolean; topK: string } | null>(null);
    const [servers, setServers] = useState<string[]>([]);
    const [folders, setFolders] = useState<string[]>([]);

    const refresh = useCallback(async () => {
        try {
            const next = await getJson<ToolsView>("/api/tools");
            setView(next);
            setSelection({ enabled: next.selection.enabled, topK: String(next.selection.top_k) });
            setServers(next.boundaries.mcp_servers.length ? next.boundaries.mcp_servers : [""]);
            const chosen = agentFolders(next);
            setFolders(chosen.length ? chosen : [""]);
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
            setNote(`${outcome.message ?? t.notSaved} ${details}`.trim());
        }
    };

    if (error) {
        return (
            <main className={styles.page}>
                <p className={styles.error}>
                    {t.unavailable} {error}
                </p>
            </main>
        );
    }

    if (!view || !selection) {
        return (
            <main className={styles.page}>
                <p className={styles.muted}>{t.loading}</p>
            </main>
        );
    }

    const tools = view.skills.flatMap((skill) => skill.tools);
    const active = tools.filter((tool) => tool.enabled).length;
    const known = new Set(tools.map((tool) => tool.name));
    const stale = view.disabled.filter((name) => !known.has(name));
    const topK = Number(selection.topK);
    const selectionDirty =
        selection.enabled !== view.selection.enabled || selection.topK !== String(view.selection.top_k);
    const topKValid = Number.isInteger(topK) && topK >= 1 && topK <= 50;
    const serversDirty = serversValue(servers) !== serversValue(view.boundaries.mcp_servers);
    const serversValid = servers.every((row) => !row.trim() || validServer(row));
    const foldersDirty = foldersValue(folders) !== foldersValue(agentFolders(view));
    const foldersValid = folders.every((row) => !row.trim() || absolutePath(row));

    const setRisk = (tool: ToolInfo, risk: Risk) =>
        apply(
            { AEHUB_MCP_TOOL_RISK: riskValue(view.mcp.risk, tool.name, risk) },
            risk === "high" ? t.riskHigh(tool.name) : t.riskLowered(tool.name, risk),
        );

    const reconnect = async () => {
        setBusy(true);
        setNote(null);
        try {
            await postJson("/api/tools/mcp/refresh", {});
            setNote(t.reconnected);
            await refresh();
        } catch (err) {
            setNote(`${t.reconnectFailed} ${message(err)}`);
        } finally {
            setBusy(false);
        }
    };

    const toggle = (tool: ToolInfo, enabled: boolean) =>
        apply(
            { AEHUB_DISABLED_TOOLS: disabledValue(view.disabled, tool.name, enabled) },
            enabled ? t.toolOn(tool.name) : t.toolOff(tool.name),
        );

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>{t.title}</h1>
                <span className={styles.badge} data-tone="ok">
                    {t.active(active, tools.length)}
                </span>
                {note && (
                    <span className={styles.muted} role="status">
                        {note}
                    </span>
                )}
            </div>

            <p className={styles.muted}>{t.gateway}</p>

            <section className={styles.card} aria-label={t.index}>
                <h2 className={styles.h2}>{t.index}</h2>
                <p className={styles.help}>{t.indexHelp}</p>
                <div className={styles.filters}>
                    <div className={styles.row} role="radiogroup" aria-label={t.index}>
                        <label className={styles.check}>
                            <input
                                type="radio"
                                name="selection"
                                checked={selection.enabled}
                                onChange={() => setSelection({ ...selection, enabled: true })}
                            />
                            {t.on}
                        </label>
                        <label className={styles.check}>
                            <input
                                type="radio"
                                name="selection"
                                checked={!selection.enabled}
                                onChange={() => setSelection({ ...selection, enabled: false })}
                            />
                            {t.off}
                        </label>
                    </div>
                    <label className={styles.field}>
                        {t.perRun}
                        <input
                            type="number"
                            min={1}
                            max={50}
                            className={styles.narrow}
                            value={selection.topK}
                            aria-invalid={!topKValid}
                            onChange={(event) => setSelection({ ...selection, topK: event.target.value })}
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
                                t.indexSaved,
                            )
                        }
                    >
                        {t.save}
                    </button>
                </div>
                <p className={styles.muted}>
                    {!view.selection.enabled
                        ? t.indexOff
                        : view.selection.active
                          ? t.indexActive(view.selection.top_k, view.selection.tools)
                          : t.indexAll(view.selection.tools, view.selection.top_k)}
                </p>
            </section>

            <section className={styles.section} aria-label={t.catalog}>
                <h2 className={styles.h2}>
                    {t.catalog} <span>{t.skills(view.skills.length)}</span>
                </h2>
                <div className={styles.grid}>
                    {view.skills.map((skill) => (
                        <SkillCard key={skill.name} skill={skill} busy={busy} onToggle={toggle} onRisk={setRisk} />
                    ))}
                </div>
                {stale.length > 0 && (
                    <div className={styles.issue} data-tone="warn">
                        <span>
                            {t.stale} <span className={styles.mono}>{stale.join(", ")}</span>
                        </span>
                        <button
                            type="button"
                            className={styles.linkBtn}
                            disabled={busy}
                            onClick={() =>
                                apply(
                                    {
                                        AEHUB_DISABLED_TOOLS:
                                            view.disabled.filter((name) => known.has(name)).join(",") || null,
                                    },
                                    t.cleaned,
                                )
                            }
                        >
                            {t.removeFromList}
                        </button>
                    </div>
                )}
            </section>

            <section className={styles.card} aria-label={t.boundaries}>
                <h2 className={styles.h2}>{t.boundaries}</h2>

                <div className={styles.setting}>
                    <span className={styles.settingLabel}>{t.folders}</span>
                    <p className={styles.help}>
                        {t.foldersHelp} <code className={styles.mono}>AEHUB_ALLOWED_DIRS</code>.
                    </p>
                    <ul className={styles.lines}>
                        {view.boundaries.directories
                            .filter((folder) => folder.kind !== "agent")
                            .map((folder) => (
                                <li key={folder.path}>
                                    <span className={styles.mono}>{folder.path}</span>
                                    <b>
                                        {t.working} · {folder.exists ? t.exists : t.notYet}
                                    </b>
                                </li>
                            ))}
                    </ul>
                    <p className={styles.help}>{t.agentFoldersHelp}</p>
                    <ul className={styles.servers}>
                        {folders.map((row, index) => (
                            <li key={index} data-invalid={Boolean(row.trim()) && !absolutePath(row)}>
                                <input
                                    className={styles.input}
                                    value={row}
                                    placeholder={"C:\\Users\\me\\Documents"}
                                    aria-label={t.folderN(index + 1)}
                                    spellCheck={false}
                                    onChange={(event) => setFolders(folders.map((item, at) => (at === index ? event.target.value : item)))}
                                />
                                <span className={styles.icons}>
                                    <button
                                        type="button"
                                        className={styles.icon}
                                        aria-label={t.removeFolder(index + 1)}
                                        onClick={() => {
                                            const next = folders.filter((_, at) => at !== index);
                                            setFolders(next.length ? next : [""]);
                                        }}
                                    >
                                        ×
                                    </button>
                                </span>
                            </li>
                        ))}
                    </ul>
                    <div className={styles.row}>
                        <button type="button" className={styles.linkBtn} onClick={() => setFolders([...folders, ""])}>
                            {t.addFolder}
                        </button>
                        <button
                            type="button"
                            className={`${styles.btn} ${styles.go}`}
                            disabled={busy || !foldersDirty || !foldersValid}
                            onClick={() => apply({ AEHUB_AGENT_FOLDERS: foldersValue(folders) }, t.foldersSaved)}
                        >
                            {t.saveFolders}
                        </button>
                        {!foldersValid && (
                            <span className={styles.error} role="alert">
                                {t.folderInvalid}
                            </span>
                        )}
                    </div>
                </div>

                <div className={styles.setting}>
                    <span className={styles.settingLabel}>{t.hosts}</span>
                    <p className={styles.help}>
                        {t.hostsHelp} <code className={styles.mono}>AEHUB_ALLOWED_HOSTS</code>.
                    </p>
                    <p className={styles.mono}>{view.boundaries.api_hosts.join(" · ")}</p>
                </div>

                <div className={styles.setting}>
                    <span className={styles.settingLabel}>{t.allowedServers}</span>
                    <p className={styles.help}>{t.serversHelp}</p>
                    <ul className={styles.servers}>
                        {servers.map((row, index) => (
                            <li key={index} data-invalid={Boolean(row.trim()) && !validServer(row)}>
                                <input
                                    className={styles.input}
                                    value={row}
                                    placeholder="https://mcp-server.example/sse"
                                    aria-label={t.serverN(index + 1)}
                                    spellCheck={false}
                                    onChange={(event) =>
                                        setServers(servers.map((item, at) => (at === index ? event.target.value : item)))
                                    }
                                />
                                <span className={styles.icons}>
                                    <button
                                        type="button"
                                        className={styles.icon}
                                        aria-label={t.removeServer(index + 1)}
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
                        <button type="button" className={styles.linkBtn} onClick={() => setServers([...servers, ""])}>
                            {t.addServer}
                        </button>
                        <button
                            type="button"
                            className={`${styles.btn} ${styles.go}`}
                            disabled={busy || !serversDirty || !serversValid}
                            onClick={() => apply({ AEHUB_MCP_ALLOWED_SERVERS: serversValue(servers) }, t.serversSaved)}
                        >
                            {t.saveServers}
                        </button>
                        {!serversValid && (
                            <span className={styles.error} role="alert">
                                {t.serverInvalid}
                            </span>
                        )}
                    </div>
                </div>

                <div className={styles.setting}>
                    <span className={styles.settingLabel}>{t.mcpServers}</span>
                    <p className={styles.help}>
                        {t.tokenHelpStart} <code className={styles.mono}>AEHUB_MCP_TOKENS</code> (
                        <code className={styles.mono}>host=token</code>, {t.tokenHelpMid}{" "}
                        <code className={styles.mono}>python scripts/aehub.py setup</code>. {t.tokenHelpEnd}
                    </p>
                    {view.mcp.servers.length ? (
                        <ul className={styles.lines} aria-label={t.serverStates}>
                            {view.mcp.servers.map((server) => {
                                const label = t.mcpStates[server.state] ?? t.mcpStates.waiting;
                                return (
                                    <li key={server.url}>
                                        <span>
                                            <span className={styles.mono}>{server.name}</span> · {server.url}
                                            {server.error && <span className={styles.help}> · {server.error}</span>}
                                        </span>
                                        <span className={styles.row}>
                                            <span className={styles.badge} data-tone={MCP_TONES[server.state] ?? "warn"}>
                                                {server.state === "connected"
                                                    ? t.connectedTools(label, server.tools.length)
                                                    : label}
                                            </span>
                                            <span className={styles.badge}>{server.token ? t.tokenSet : t.noToken}</span>
                                        </span>
                                    </li>
                                );
                            })}
                        </ul>
                    ) : (
                        <p className={styles.muted}>{t.noServers}</p>
                    )}
                    <div className={styles.row}>
                        <button
                            type="button"
                            className={styles.btn}
                            disabled={busy || !view.mcp.servers.length}
                            onClick={reconnect}
                        >
                            {t.reconnect}
                        </button>
                    </div>
                </div>
            </section>

            <TrashCard />

            <section className={styles.card} aria-label={t.sandbox}>
                <h2 className={styles.h2}>{t.sandbox}</h2>
                <dl className={styles.facts}>
                    <dt>Docker</dt>
                    <dd>
                        <span className={styles.badge} data-tone={view.sandbox.docker ? "ok" : "warn"}>
                            {view.sandbox.docker ? t.dockerOk : t.dockerMissing}
                        </span>
                    </dd>
                    <dt>{t.image}</dt>
                    <dd className={styles.mono}>{view.sandbox.image}</dd>
                    <dt>{t.memory}</dt>
                    <dd className={styles.mono}>{view.sandbox.memory_limit}</dd>
                    <dt>{t.net}</dt>
                    <dd>{view.sandbox.network ? t.netOn : t.netOff}</dd>
                </dl>
            </section>
        </main>
    );
}
