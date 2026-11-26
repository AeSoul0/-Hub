/**
 * @file frontend/src/app/control-plane/system/page.tsx
 * @description System (F9, ADR-030): the state of the engine and what it
 * runs on, the startup parameters read only, memory, desktop updates, the
 * flight recorder, the evals, the access key, the recent warnings and the
 * API's own pages (documentation, metrics, health; F10).
 *
 * Everything comes from /api/system (admin only). The evals run offline in
 * a child process of the backend; the page follows a run while it lasts.
 */
"use client";

import React, { useCallback, useEffect, useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import { API_BASE_URL, fetchApi, getJson, postJson } from "@/lib/api/client";
import {
    apiPages,
    bytesText,
    evalStatus,
    eventTime,
    MEMORY_LABELS,
    MEMORY_ORDER,
    METRIC_LABELS,
    metricText,
    PARAMETER_LABELS,
    recorderQuery,
    schemaText,
    SOURCE_LABELS,
    uptimeText,
    voiceText,
    type EvalState,
    type LogEntry,
    type RecorderFilters,
    type RecorderResult,
    type SystemView,
    type UpdateCheck,
} from "@/lib/api/system";
import { catalog, useLanguage, useText } from "@/lib/i18n";
import { describe } from "@/lib/nucleo/engine";
import { localTime } from "@/lib/nucleo/runs";

// While an evaluation runs, its state is read this often.
const EVAL_POLL_MS = 3000;

const TEXT = catalog({
    en: {
        application: "Application",
        desktopApp: "desktop app",
        server: "server",
        version: "Version",
        notGiven: "not given",
        upFor: "Up for",
        reachable: "reachable",
        notAnswering: "not answering",
        type: "Type",
        response: "Response",
        schema: "Schema",
        eventBus: "Event bus",
        busOn: "on",
        busMemory: "In memory, inside the backend.",
        busRedis: "Redis: events go through the Redis server.",
        updatesDesktop: "The app looks for a signed update at every start and installs it only if you say yes.",
        updatesServer: "Automatic updates belong to the desktop app; here you only see the latest published version.",
        checking: "Checking…",
        checkNow: "Check now",
        checkFailed: "Check failed:",
        newer: (latest: string | null, current: string | null) =>
            `ÆHub ${latest} is available (this is ${current}): restart the app to install it.`,
        latest: (latest: string | null) => `You have the latest version (${latest}).`,
        published: (latest: string | null) => `The latest published version is ${latest}.`,
        processMemory: "Process memory",
        process: "Process",
        processes: "Processes",
        total: "ÆHub total",
        free: (available: string, total: string) => `Free on the computer: ${available} of ${total}.`,
        noVoice: "No local model in memory.",
        inMemory: (models: string) => `In memory: ${models}.`,
        voiceIdle: "How long before they are released is chosen in VOICE.",
        startupHelp: "Read at start: they change only when ÆHub restarts. Passwords are never shown.",
        startupParameters: "Startup parameters",
        parameter: "Parameter",
        value: "Value",
        origin: "Origin",
        apiHelp: "Pages of the API itself, without login: they answer on the API host, that is on this computer.",
        apiPages: "API pages",
        exportFailed: "Export failed:",
        searchRecorder: "Search the flight recorder",
        text: "Text",
        eventType: "Type",
        run: "Run",
        search: "Search",
        export: "Export as JSONL",
        found: (matched: number) => `${matched} events found`,
        newest: (count: number) => `, here the ${count} most recent`,
        fileOf: (size: string) => ` · file of ${size}.`,
        foundEvents: "Events found",
        time: "Time",
        event: "Event",
        detail: "Detail",
        running: "Running…",
        startEvals: "Run the evals",
        evalsHelp:
            "Offline: simulated models, in-memory database, no cost. They run in a separate process, so real runs go on.",
        baseline: "The result is compared with the baseline: it is the check that blocks a release.",
        noBaseline: "Without a baseline (desktop app) there is only the report.",
        finished: (at: string, passed: number, total: number) => `Finished ${at}, ${passed} of ${total} cases passed.`,
        metrics: "Eval metrics",
        regressions: "Regressions",
        failedCases: "Failed cases",
        critical: "critical",
        keyFromEnv: "Here the key comes from the environment",
        keyFromEnvRest: ": change it where it is set, then restart. In the desktop app it is changed from here.",
        keyHelp:
            "The key is for signing in from a browser; the desktop app does not use it. Changing it closes every other session; this one stays open.",
        newKey: "New key, shown only now: copy it somewhere safe.",
        sessionsClosed: (count: number) => `Sessions closed: ${count}.`,
        confirmRotate: "Close every other session and change the key?",
        confirm: "Confirm: change the key",
        cancel: "Cancel",
        rotate: "Change the key",
        logsHelp: "Backend warnings and errors since the last start, newest first.",
        refresh: "Refresh",
        noLogs: "No warnings.",
        logs: "Warnings and errors",
        title: "SYSTEM",
        unavailable: "System not available:",
        reading: "Reading the state…",
        sections: {
            state: "STATE",
            memory: "MEMORY",
            updates: "UPDATES",
            recorder: "FLIGHT RECORDER",
            evals: "EVALS",
            key: "ACCESS KEY",
            logs: "WARNINGS",
            startup: "STARTUP PARAMETERS",
            api: "API",
        },
    },
    it: {
        application: "Applicazione",
        desktopApp: "app desktop",
        server: "server",
        version: "Versione",
        notGiven: "non indicata",
        upFor: "Attivo da",
        reachable: "raggiungibile",
        notAnswering: "non risponde",
        type: "Tipo",
        response: "Risposta",
        schema: "Schema",
        eventBus: "Bus degli eventi",
        busOn: "attivo",
        busMemory: "In memoria, dentro il backend.",
        busRedis: "Redis: gli eventi passano dal server Redis.",
        updatesDesktop: "L'app cerca un aggiornamento firmato a ogni avvio e lo installa solo se rispondi di sì.",
        updatesServer:
            "Gli aggiornamenti automatici sono dell'app desktop; qui si vede solo l'ultima versione pubblicata.",
        checking: "Controllo…",
        checkNow: "Controlla adesso",
        checkFailed: "Controllo non riuscito:",
        newer: (latest: string | null, current: string | null) =>
            `È disponibile ÆHub ${latest} (questa è la ${current}): riavvia l'app per installarla.`,
        latest: (latest: string | null) => `Sei all'ultima versione (${latest}).`,
        published: (latest: string | null) => `L'ultima versione pubblicata è la ${latest}.`,
        processMemory: "Memoria dei processi",
        process: "Processo",
        processes: "Processi",
        total: "Totale di ÆHub",
        free: (available: string, total: string) => `Libera sul computer: ${available} su ${total}.`,
        noVoice: "Nessun modello locale in memoria.",
        inMemory: (models: string) => `In memoria: ${models}.`,
        voiceIdle: "Il tempo dopo cui si liberano si sceglie in VOCE.",
        startupHelp: "Si leggono all'avvio: cambiano solo riavviando ÆHub. Le password non si vedono mai.",
        startupParameters: "Parametri di avvio",
        parameter: "Parametro",
        value: "Valore",
        origin: "Origine",
        apiHelp:
            "Pagine dell'API stessa, senza accesso: rispondono sull'host dell'API, cioè su questo computer.",
        apiPages: "Pagine dell'API",
        exportFailed: "Esportazione non riuscita:",
        searchRecorder: "Cerca nel flight recorder",
        text: "Testo",
        eventType: "Tipo",
        run: "Run",
        search: "Cerca",
        export: "Esporta in JSONL",
        found: (matched: number) => `${matched} eventi trovati`,
        newest: (count: number) => `, qui i ${count} più recenti`,
        fileOf: (size: string) => ` · file di ${size}.`,
        foundEvents: "Eventi trovati",
        time: "Ora",
        event: "Evento",
        detail: "Dettaglio",
        running: "In corso…",
        startEvals: "Avvia gli eval",
        evalsHelp:
            "Offline: modelli simulati, database in memoria, nessun costo. Girano in un processo a parte, quindi le run vere continuano.",
        baseline: "Il risultato si confronta con la baseline: è il controllo che blocca una release.",
        noBaseline: "Senza baseline (app desktop) c'è solo il rapporto.",
        finished: (at: string, passed: number, total: number) =>
            `Finiti ${at}, ${passed} casi su ${total} superati.`,
        metrics: "Metriche degli eval",
        regressions: "Regressioni",
        failedCases: "Casi non superati",
        critical: "critico",
        keyFromEnv: "Qui la chiave viene dall'ambiente",
        keyFromEnvRest: ": si cambia dove è impostata, poi si riavvia. Nell'app desktop si cambia da qui.",
        keyHelp:
            "La chiave serve per entrare da un browser; l'app desktop non la usa. Cambiandola, tutte le altre sessioni vengono chiuse; questa resta aperta.",
        newKey: "Nuova chiave, la vedi solo adesso: copiala in un posto sicuro.",
        sessionsClosed: (count: number) => `Sessioni chiuse: ${count}.`,
        confirmRotate: "Chiudere tutte le altre sessioni e cambiare la chiave?",
        confirm: "Conferma: cambia la chiave",
        cancel: "Annulla",
        rotate: "Cambia la chiave",
        logsHelp: "Avvisi ed errori del backend dall'ultimo avvio, i più recenti per primi.",
        refresh: "Aggiorna",
        noLogs: "Nessun avviso.",
        logs: "Avvisi ed errori",
        title: "SISTEMA",
        unavailable: "Sistema non disponibile:",
        reading: "Leggo lo stato…",
        sections: {
            state: "STATO",
            memory: "MEMORIA",
            updates: "AGGIORNAMENTI",
            recorder: "FLIGHT RECORDER",
            evals: "EVAL",
            key: "CHIAVE DI ACCESSO",
            logs: "AVVISI",
            startup: "PARAMETRI DI AVVIO",
            api: "API",
        },
    },
});

function message(err: unknown): string {
    return err instanceof Error ? err.message : String(err);
}

function Health({ ok, label }: { ok: boolean; label: string }) {
    return (
        <span className={styles.badge} data-tone={ok ? "ok" : "bad"}>
            {label}
        </span>
    );
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
    return (
        <section className={styles.section} aria-labelledby={id}>
            <h2 id={id} className={styles.h2}>
                {title}
            </h2>
            {children}
        </section>
    );
}

function StatusCards({ view }: { view: SystemView }) {
    const lang = useLanguage();
    const t = TEXT[lang];
    const { app, database, event_bus: bus } = view;
    return (
        <div className={styles.grid}>
            <article className={styles.card} aria-label={t.application}>
                <div className={styles.row}>
                    <b>ÆHub</b>
                    <span className={styles.badge}>{app.desktop ? t.desktopApp : t.server}</span>
                </div>
                <dl className={styles.facts}>
                    <dt>{t.version}</dt>
                    <dd className={styles.mono}>{app.version ?? t.notGiven}</dd>
                    <dt>{t.upFor}</dt>
                    <dd>{uptimeText(app.uptime_seconds, lang)}</dd>
                    <dt>Python</dt>
                    <dd className={styles.mono}>{app.python}</dd>
                </dl>
            </article>
            <article className={styles.card} aria-label="Database">
                <div className={styles.row}>
                    <b>Database</b>
                    <Health ok={database.ok} label={database.ok ? t.reachable : t.notAnswering} />
                </div>
                <dl className={styles.facts}>
                    <dt>{t.type}</dt>
                    <dd className={styles.mono}>{database.dialect}</dd>
                    <dt>{t.response}</dt>
                    <dd className={styles.mono}>{database.latency_ms != null ? `${database.latency_ms} ms` : "-"}</dd>
                    <dt>{t.schema}</dt>
                    <dd className={styles.mono}>{schemaText(database.revision, database.head, lang)}</dd>
                </dl>
                {database.error && <p className={styles.error}>{database.error}</p>}
            </article>
            <article className={styles.card} aria-label={t.eventBus}>
                <div className={styles.row}>
                    <b>{t.eventBus}</b>
                    <Health ok={bus.ok} label={bus.ok ? t.busOn : t.notAnswering} />
                </div>
                <p className={styles.muted}>{bus.kind === "memory" ? t.busMemory : t.busRedis}</p>
                {bus.error && <p className={styles.error}>{bus.error}</p>}
            </article>
        </div>
    );
}

function Updates({ view }: { view: SystemView }) {
    const t = useText(TEXT);
    const [check, setCheck] = useState<UpdateCheck | null>(null);
    const [busy, setBusy] = useState(false);

    const run = async () => {
        setBusy(true);
        try {
            setCheck(await postJson<UpdateCheck>("/api/system/updates/check", {}));
        } catch (err) {
            setCheck({ current: null, latest: null, newer: null, published_at: null, notes: null, error: message(err) });
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className={styles.card}>
            <p className={styles.muted}>{view.app.desktop ? t.updatesDesktop : t.updatesServer}</p>
            <div className={styles.row}>
                <button type="button" className={styles.btn} disabled={busy} onClick={() => void run()}>
                    {busy ? t.checking : t.checkNow}
                </button>
            </div>
            {check?.error && (
                <p className={styles.error}>
                    {t.checkFailed} {check.error}
                </p>
            )}
            {check && !check.error && (
                <p data-testid="update-result">
                    {check.newer === true
                        ? t.newer(check.latest, check.current)
                        : check.newer === false
                          ? t.latest(check.latest)
                          : t.published(check.latest)}
                </p>
            )}
            {check?.notes && <pre className={styles.pre}>{check.notes}</pre>}
        </div>
    );
}

function Memory({ view }: { view: SystemView }) {
    const lang = useLanguage();
    const t = TEXT[lang];
    const { memory } = view;
    return (
        <div className={styles.card}>
            <div className={styles.tableWrap}>
                <table className={styles.table} aria-label={t.processMemory}>
                    <thead>
                        <tr>
                            <th>{t.process}</th>
                            <th className={styles.num}>{t.processes}</th>
                            <th className={styles.num}>RAM</th>
                        </tr>
                    </thead>
                    <tbody>
                        {MEMORY_ORDER.filter((kind) => kind === "backend" || memory.groups[kind]?.processes > 0).map(
                            (kind) => (
                                <tr key={kind}>
                                    <td>{MEMORY_LABELS[lang][kind]}</td>
                                    <td className={styles.num}>{memory.groups[kind].processes}</td>
                                    <td className={styles.num}>{bytesText(memory.groups[kind].bytes, lang)}</td>
                                </tr>
                            ),
                        )}
                        <tr>
                            <td>
                                <b>{t.total}</b>
                            </td>
                            <td />
                            <td className={styles.num}>
                                <b>{bytesText(memory.total_bytes, lang)}</b>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <p className={styles.muted}>
                {t.free(bytesText(memory.machine.available_bytes, lang), bytesText(memory.machine.total_bytes, lang))}
            </p>
            <p className={styles.muted}>
                {memory.voice.length === 0
                    ? t.noVoice
                    : t.inMemory(memory.voice.map((voice) => voiceText(voice, lang)).join("; "))}{" "}
                {t.voiceIdle}
            </p>
        </div>
    );
}

function Startup({ view }: { view: SystemView }) {
    const lang = useLanguage();
    const t = TEXT[lang];
    return (
        <div className={styles.card}>
            <p className={styles.muted}>{t.startupHelp}</p>
            <div className={styles.tableWrap}>
                <table className={styles.table} aria-label={t.startupParameters}>
                    <thead>
                        <tr>
                            <th>{t.parameter}</th>
                            <th>{t.value}</th>
                            <th>{t.origin}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {view.startup.map((item) => (
                            <tr key={item.name}>
                                <td>
                                    {PARAMETER_LABELS[lang][item.name] ?? item.name}
                                    <span className={`${styles.sub} ${styles.mono}`}>{item.name}</span>
                                </td>
                                <td className={styles.mono}>{item.value ?? <span className={styles.faint}>-</span>}</td>
                                <td>{SOURCE_LABELS[lang][item.source]}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function ApiPages() {
    const lang = useLanguage();
    const t = TEXT[lang];
    return (
        <div className={styles.card}>
            <p className={styles.muted}>{t.apiHelp}</p>
            <ul className={styles.lines} aria-label={t.apiPages}>
                {apiPages(lang).map((page) => (
                    <li key={page.path}>
                        <a
                            className={styles.link}
                            href={new URL(page.path, API_BASE_URL).toString()}
                            target="_blank"
                            rel="noreferrer"
                        >
                            {page.label}
                        </a>{" "}
                        <span className={styles.mono}>{page.path}</span> <span className={styles.faint}>· {page.help}</span>
                    </li>
                ))}
            </ul>
        </div>
    );
}

function Recorder() {
    const lang = useLanguage();
    const t = TEXT[lang];
    const [filters, setFilters] = useState<RecorderFilters>({ q: "", event_type: "", run_id: "" });
    const [result, setResult] = useState<RecorderResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const search = async (event?: React.FormEvent) => {
        event?.preventDefault();
        setBusy(true);
        setError(null);
        try {
            setResult(await getJson<RecorderResult>(`/api/system/events${recorderQuery(filters)}`));
        } catch (err) {
            setError(message(err));
        } finally {
            setBusy(false);
        }
    };

    const exportFile = async () => {
        setError(null);
        try {
            const response = await fetchApi(`/api/system/events/export${recorderQuery(filters)}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const disposition = response.headers.get("Content-Disposition") ?? "";
            const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "aehub-flight-recorder.jsonl";
            const url = URL.createObjectURL(await response.blob());
            const link = document.createElement("a");
            link.href = url;
            link.download = name;
            link.click();
            URL.revokeObjectURL(url);
        } catch (err) {
            setError(`${t.exportFailed} ${message(err)}`);
        }
    };

    return (
        <div className={styles.card}>
            <form className={styles.filters} onSubmit={(event) => void search(event)} aria-label={t.searchRecorder}>
                <label className={styles.field}>
                    {t.text}
                    <input value={filters.q} onChange={(event) => setFilters({ ...filters, q: event.target.value })} />
                </label>
                <label className={styles.field}>
                    {t.eventType}
                    <input
                        placeholder="tool, checker.rejected…"
                        value={filters.event_type}
                        onChange={(event) => setFilters({ ...filters, event_type: event.target.value })}
                    />
                </label>
                <label className={styles.field}>
                    {t.run}
                    <input value={filters.run_id} onChange={(event) => setFilters({ ...filters, run_id: event.target.value })} />
                </label>
                <div className={styles.row}>
                    <button type="submit" className={styles.btn} disabled={busy}>
                        {t.search}
                    </button>
                    <button type="button" className={styles.linkBtn} onClick={() => void exportFile()}>
                        {t.export}
                    </button>
                </div>
            </form>
            {error && <p className={styles.error}>{error}</p>}
            {result && (
                <>
                    <p className={styles.muted}>
                        {t.found(result.matched)}
                        {result.truncated ? t.newest(result.events.length) : ""}
                        {t.fileOf(bytesText(result.file_bytes, lang))}
                    </p>
                    {result.events.length > 0 && (
                        <div className={styles.tableWrap}>
                            <table className={styles.table} aria-label={t.foundEvents}>
                                <thead>
                                    <tr>
                                        <th>{t.time}</th>
                                        <th>{t.event}</th>
                                        <th>{t.detail}</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {result.events.map((event, index) => (
                                        <tr key={`${event.run_id}-${event.timestamp}-${index}`}>
                                            <td className={styles.mono}>{eventTime(event.timestamp)}</td>
                                            <td className={styles.mono}>{event.event_type}</td>
                                            <td>{describe(event, lang).detail}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

function Evals() {
    const lang = useLanguage();
    const t = TEXT[lang];
    const [state, setState] = useState<EvalState | null>(null);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            setState(await getJson<EvalState>("/api/system/evals"));
        } catch (err) {
            setError(message(err));
        }
    }, []);

    useEffect(() => {
        const first = setTimeout(() => void load(), 0);
        return () => clearTimeout(first);
    }, [load]);

    useEffect(() => {
        if (state?.status !== "running") {
            return;
        }
        const timer = setInterval(() => void load(), EVAL_POLL_MS);
        return () => clearInterval(timer);
    }, [state?.status, load]);

    const start = async () => {
        setError(null);
        try {
            setState(await postJson<EvalState>("/api/system/evals", {}));
        } catch (err) {
            setError(message(err));
        }
    };

    const badge = state ? evalStatus(state.status, lang) : null;
    const failed = state?.cases.filter((item) => !item.passed) ?? [];

    return (
        <div className={styles.card}>
            <div className={styles.row}>
                {badge && (
                    <span className={styles.badge} data-tone={badge.tone || undefined} data-testid="eval-status">
                        {badge.label}
                    </span>
                )}
                <button
                    type="button"
                    className={styles.btn}
                    disabled={!state || state.status === "running"}
                    onClick={() => void start()}
                >
                    {state?.status === "running" ? t.running : t.startEvals}
                </button>
            </div>
            <p className={styles.help}>
                {t.evalsHelp} {state?.baseline ? t.baseline : t.noBaseline}
            </p>
            {error && <p className={styles.error}>{error}</p>}
            {state?.error && <pre className={`${styles.pre} ${styles.error}`}>{state.error}</pre>}
            {state?.finished_at && (
                <p className={styles.muted}>
                    {t.finished(localTime(state.finished_at, lang), state.cases.length - failed.length, state.cases.length)}
                </p>
            )}
            {state && Object.keys(state.metrics).length > 0 && (
                <dl className={styles.facts} aria-label={t.metrics}>
                    {Object.entries(state.metrics).map(([name, value]) => (
                        <React.Fragment key={name}>
                            <dt>{METRIC_LABELS[lang][name] ?? name}</dt>
                            <dd className={styles.mono}>{metricText(name, value, lang)}</dd>
                        </React.Fragment>
                    ))}
                </dl>
            )}
            {state && state.problems.length > 0 && (
                <ul className={styles.lines} aria-label={t.regressions}>
                    {state.problems.map((problem) => (
                        <li key={problem} className={styles.error}>
                            {problem}
                        </li>
                    ))}
                </ul>
            )}
            {failed.length > 0 && (
                <ul className={styles.lines} aria-label={t.failedCases}>
                    {failed.map((item) => (
                        <li key={item.id}>
                            <span className={styles.mono}>{item.id}</span>
                            {item.critical && (
                                <span className={styles.badge} data-tone="bad">
                                    {t.critical}
                                </span>
                            )}
                            {item.failures.length > 0 && <span className={styles.sub}>{item.failures.join(" · ")}</span>}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

function AccessKey({ view }: { view: SystemView }) {
    const t = useText(TEXT);
    const [confirming, setConfirming] = useState(false);
    const [rotated, setRotated] = useState<{ key: string; sessions_closed: number } | null>(null);
    const [error, setError] = useState<string | null>(null);

    const rotate = async () => {
        setConfirming(false);
        setError(null);
        try {
            setRotated(
                await postJson<{ key: string; sessions_closed: number }>("/api/system/access-key/rotate", {
                    confirm: true,
                }),
            );
        } catch (err) {
            setError(message(err));
        }
    };

    if (!view.access_key.can_rotate) {
        return (
            <div className={styles.card}>
                <p className={styles.muted}>
                    {t.keyFromEnv} (<span className={styles.mono}>AEHUB_SECRET_KEY</span>){t.keyFromEnvRest}
                </p>
            </div>
        );
    }

    return (
        <div className={styles.card}>
            <p className={styles.muted}>{t.keyHelp}</p>
            {rotated ? (
                <div className={`${styles.card} ${styles.amber}`} role="status">
                    <p>{t.newKey}</p>
                    <pre className={styles.pre} data-testid="new-key">
                        {rotated.key}
                    </pre>
                    <p className={styles.muted}>{t.sessionsClosed(rotated.sessions_closed)}</p>
                </div>
            ) : confirming ? (
                <div className={styles.row}>
                    <span className={styles.warn}>{t.confirmRotate}</span>
                    <button type="button" className={`${styles.btn} ${styles.danger}`} onClick={() => void rotate()}>
                        {t.confirm}
                    </button>
                    <button type="button" className={styles.linkBtn} onClick={() => setConfirming(false)}>
                        {t.cancel}
                    </button>
                </div>
            ) : (
                <div className={styles.row}>
                    <button type="button" className={styles.btn} onClick={() => setConfirming(true)}>
                        {t.rotate}
                    </button>
                </div>
            )}
            {error && <p className={styles.error}>{error}</p>}
        </div>
    );
}

function Logs() {
    const lang = useLanguage();
    const t = TEXT[lang];
    const [logs, setLogs] = useState<LogEntry[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            setLogs((await getJson<{ logs: LogEntry[] }>("/api/system/logs")).logs);
            setError(null);
        } catch (err) {
            setError(message(err));
        }
    }, []);

    useEffect(() => {
        const first = setTimeout(() => void load(), 0);
        return () => clearTimeout(first);
    }, [load]);

    return (
        <div className={styles.card}>
            <div className={styles.row}>
                <p className={styles.muted}>{t.logsHelp}</p>
                <button type="button" className={styles.linkBtn} onClick={() => void load()}>
                    {t.refresh}
                </button>
            </div>
            {error && <p className={styles.error}>{error}</p>}
            {logs && logs.length === 0 && <p className={styles.muted}>{t.noLogs}</p>}
            {logs && logs.length > 0 && (
                <ul className={styles.lines} aria-label={t.logs}>
                    {logs.map((entry, index) => (
                        <li key={`${entry.at}-${index}`} className={entry.level === "warning" ? styles.warn : styles.error}>
                            <span className={styles.mono}>
                                {localTime(entry.at, lang)} · {entry.logger}
                            </span>{" "}
                            {entry.message}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

export default function SystemPage() {
    const t = useText(TEXT);
    const [view, setView] = useState<SystemView | null>(null);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            setView(await getJson<SystemView>("/api/system"));
            setError(null);
        } catch (err) {
            setError(message(err));
        }
    }, []);

    useEffect(() => {
        const first = setTimeout(() => void load(), 0);
        return () => clearTimeout(first);
    }, [load]);

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>{t.title}</h1>
                <button type="button" className={styles.linkBtn} onClick={() => void load()}>
                    {t.refresh}
                </button>
            </div>

            {error && (
                <p className={styles.error}>
                    {t.unavailable} {error}
                </p>
            )}
            {!view && !error && <p className={styles.muted}>{t.reading}</p>}

            {view && (
                <div className={styles.stack}>
                    <Section id="state-title" title={t.sections.state}>
                        <StatusCards view={view} />
                    </Section>
                    <Section id="memory-title" title={t.sections.memory}>
                        <Memory view={view} />
                    </Section>
                    <Section id="updates-title" title={t.sections.updates}>
                        <Updates view={view} />
                    </Section>
                    <Section id="recorder-title" title={t.sections.recorder}>
                        <Recorder />
                    </Section>
                    <Section id="evals-title" title={t.sections.evals}>
                        <Evals />
                    </Section>
                    <Section id="key-title" title={t.sections.key}>
                        <AccessKey view={view} />
                    </Section>
                    <Section id="logs-title" title={t.sections.logs}>
                        <Logs />
                    </Section>
                    <Section id="startup-title" title={t.sections.startup}>
                        <Startup view={view} />
                    </Section>
                    <Section id="api-title" title={t.sections.api}>
                        <ApiPages />
                    </Section>
                </div>
            )}
        </main>
    );
}
