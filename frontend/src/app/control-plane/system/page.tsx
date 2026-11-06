/**
 * @file frontend/src/app/control-plane/system/page.tsx
 * @description System (F9, ADR-030): the state of the engine and what it
 * runs on, the startup parameters read only, memory, desktop updates, the
 * flight recorder, the evals, the access key and the recent warnings.
 *
 * Everything comes from /api/system (admin only). The evals run offline in
 * a child process of the backend; the page follows a run while it lasts.
 */
"use client";

import React, { useCallback, useEffect, useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import { fetchApi, getJson, postJson } from "@/lib/api/client";
import {
    bytesText,
    EVAL_STATUS,
    eventTime,
    MEMORY_LABELS,
    MEMORY_ORDER,
    METRIC_LABELS,
    metricText,
    PARAMETER_LABELS,
    recorderQuery,
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
import { describe } from "@/lib/nucleo/engine";
import { localTime } from "@/lib/nucleo/runs";

// While an evaluation runs, its state is read this often.
const EVAL_POLL_MS = 3000;

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
    const { app, database, event_bus: bus } = view;
    return (
        <div className={styles.grid}>
            <article className={styles.card} aria-label="Applicazione">
                <div className={styles.row}>
                    <b>ÆHub</b>
                    <span className={styles.badge}>{app.desktop ? "app desktop" : "server"}</span>
                </div>
                <dl className={styles.facts}>
                    <dt>Versione</dt>
                    <dd className={styles.mono}>{app.version ?? "non indicata"}</dd>
                    <dt>Attivo da</dt>
                    <dd>{uptimeText(app.uptime_seconds)}</dd>
                    <dt>Python</dt>
                    <dd className={styles.mono}>{app.python}</dd>
                </dl>
            </article>
            <article className={styles.card} aria-label="Database">
                <div className={styles.row}>
                    <b>Database</b>
                    <Health ok={database.ok} label={database.ok ? "raggiungibile" : "non risponde"} />
                </div>
                <dl className={styles.facts}>
                    <dt>Tipo</dt>
                    <dd className={styles.mono}>{database.dialect}</dd>
                    <dt>Risposta</dt>
                    <dd className={styles.mono}>{database.latency_ms != null ? `${database.latency_ms} ms` : "-"}</dd>
                </dl>
                {database.error && <p className={styles.error}>{database.error}</p>}
            </article>
            <article className={styles.card} aria-label="Bus degli eventi">
                <div className={styles.row}>
                    <b>Bus degli eventi</b>
                    <Health ok={bus.ok} label={bus.ok ? "attivo" : "non risponde"} />
                </div>
                <p className={styles.muted}>
                    {bus.kind === "memory" ? "In memoria, dentro il backend." : "Redis: gli eventi passano dal server Redis."}
                </p>
                {bus.error && <p className={styles.error}>{bus.error}</p>}
            </article>
        </div>
    );
}

function Updates({ view }: { view: SystemView }) {
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
            <p className={styles.muted}>
                {view.app.desktop
                    ? "L'app cerca un aggiornamento firmato a ogni avvio e lo installa solo se rispondi di sì."
                    : "Gli aggiornamenti automatici sono dell'app desktop; qui si vede solo l'ultima versione pubblicata."}
            </p>
            <div className={styles.row}>
                <button type="button" className={styles.btn} disabled={busy} onClick={() => void run()}>
                    {busy ? "Controllo…" : "Controlla adesso"}
                </button>
            </div>
            {check?.error && <p className={styles.error}>Controllo non riuscito: {check.error}</p>}
            {check && !check.error && (
                <p data-testid="update-result">
                    {check.newer === true
                        ? `È disponibile ÆHub ${check.latest} (questa è la ${check.current}): riavvia l'app per installarla.`
                        : check.newer === false
                          ? `Sei all'ultima versione (${check.latest}).`
                          : `L'ultima versione pubblicata è la ${check.latest}.`}
                </p>
            )}
            {check?.notes && <pre className={styles.pre}>{check.notes}</pre>}
        </div>
    );
}

function Memory({ view }: { view: SystemView }) {
    const { memory } = view;
    return (
        <div className={styles.card}>
            <div className={styles.tableWrap}>
                <table className={styles.table} aria-label="Memoria dei processi">
                    <thead>
                        <tr>
                            <th>Processo</th>
                            <th className={styles.num}>Processi</th>
                            <th className={styles.num}>RAM</th>
                        </tr>
                    </thead>
                    <tbody>
                        {MEMORY_ORDER.filter((kind) => kind === "backend" || memory.groups[kind]?.processes > 0).map((kind) => (
                            <tr key={kind}>
                                <td>{MEMORY_LABELS[kind]}</td>
                                <td className={styles.num}>{memory.groups[kind].processes}</td>
                                <td className={styles.num}>{bytesText(memory.groups[kind].bytes)}</td>
                            </tr>
                        ))}
                        <tr>
                            <td>
                                <b>Totale di ÆHub</b>
                            </td>
                            <td />
                            <td className={styles.num}>
                                <b>{bytesText(memory.total_bytes)}</b>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <p className={styles.muted}>
                Libera sul computer: {bytesText(memory.machine.available_bytes)} su {bytesText(memory.machine.total_bytes)}.
            </p>
            <p className={styles.muted}>
                {memory.voice.length === 0
                    ? "Nessun modello vocale in memoria."
                    : `In memoria: ${memory.voice.map(voiceText).join("; ")}.`}{" "}
                Il tempo dopo cui si liberano si sceglie in VOCE.
            </p>
        </div>
    );
}

function Startup({ view }: { view: SystemView }) {
    return (
        <div className={styles.card}>
            <p className={styles.muted}>Si leggono all&apos;avvio: cambiano solo riavviando ÆHub. Le password non si vedono mai.</p>
            <div className={styles.tableWrap}>
                <table className={styles.table} aria-label="Parametri di avvio">
                    <thead>
                        <tr>
                            <th>Parametro</th>
                            <th>Valore</th>
                            <th>Origine</th>
                        </tr>
                    </thead>
                    <tbody>
                        {view.startup.map((item) => (
                            <tr key={item.name}>
                                <td>
                                    {PARAMETER_LABELS[item.name] ?? item.name}
                                    <span className={`${styles.sub} ${styles.mono}`}>{item.name}</span>
                                </td>
                                <td className={styles.mono}>{item.value ?? <span className={styles.faint}>-</span>}</td>
                                <td>{SOURCE_LABELS[item.source]}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function Recorder() {
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
            setError(`Esportazione non riuscita: ${message(err)}`);
        }
    };

    return (
        <div className={styles.card}>
            <form className={styles.filters} onSubmit={(event) => void search(event)} aria-label="Cerca nel flight recorder">
                <label className={styles.field}>
                    Testo
                    <input value={filters.q} onChange={(event) => setFilters({ ...filters, q: event.target.value })} />
                </label>
                <label className={styles.field}>
                    Tipo
                    <input
                        placeholder="tool, checker.rejected…"
                        value={filters.event_type}
                        onChange={(event) => setFilters({ ...filters, event_type: event.target.value })}
                    />
                </label>
                <label className={styles.field}>
                    Run
                    <input value={filters.run_id} onChange={(event) => setFilters({ ...filters, run_id: event.target.value })} />
                </label>
                <div className={styles.row}>
                    <button type="submit" className={styles.btn} disabled={busy}>
                        Cerca
                    </button>
                    <button type="button" className={styles.linkBtn} onClick={() => void exportFile()}>
                        Esporta in JSONL
                    </button>
                </div>
            </form>
            {error && <p className={styles.error}>{error}</p>}
            {result && (
                <>
                    <p className={styles.muted}>
                        {result.matched} eventi trovati
                        {result.truncated ? `, qui i ${result.events.length} più recenti` : ""} · file di {bytesText(result.file_bytes)}.
                    </p>
                    {result.events.length > 0 && (
                        <div className={styles.tableWrap}>
                            <table className={styles.table} aria-label="Eventi trovati">
                                <thead>
                                    <tr>
                                        <th>Ora</th>
                                        <th>Evento</th>
                                        <th>Dettaglio</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {result.events.map((event, index) => (
                                        <tr key={`${event.run_id}-${event.timestamp}-${index}`}>
                                            <td className={styles.mono}>{eventTime(event.timestamp)}</td>
                                            <td className={styles.mono}>{event.event_type}</td>
                                            <td>{describe(event).detail}</td>
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

    const badge = state ? EVAL_STATUS[state.status] : null;
    const failed = state?.cases.filter((item) => !item.passed) ?? [];

    return (
        <div className={styles.card}>
            <div className={styles.row}>
                {badge && (
                    <span className={styles.badge} data-tone={badge.tone || undefined} data-testid="eval-status">
                        {badge.label}
                    </span>
                )}
                <button type="button" className={styles.btn} disabled={!state || state.status === "running"} onClick={() => void start()}>
                    {state?.status === "running" ? "In corso…" : "Avvia gli eval"}
                </button>
            </div>
            <p className={styles.help}>
                Offline: modelli simulati, database in memoria, nessun costo. Girano in un processo a parte, quindi le run vere
                continuano.{" "}
                {state?.baseline
                    ? "Il risultato si confronta con la baseline: è il controllo che blocca una release."
                    : "Senza baseline (app desktop) c'è solo il rapporto."}
            </p>
            {error && <p className={styles.error}>{error}</p>}
            {state?.error && <pre className={`${styles.pre} ${styles.error}`}>{state.error}</pre>}
            {state?.finished_at && (
                <p className={styles.muted}>
                    Finiti {localTime(state.finished_at)}, {state.cases.length - failed.length} casi su {state.cases.length} superati.
                </p>
            )}
            {state && Object.keys(state.metrics).length > 0 && (
                <dl className={styles.facts} aria-label="Metriche degli eval">
                    {Object.entries(state.metrics).map(([name, value]) => (
                        <React.Fragment key={name}>
                            <dt>{METRIC_LABELS[name] ?? name}</dt>
                            <dd className={styles.mono}>{metricText(name, value)}</dd>
                        </React.Fragment>
                    ))}
                </dl>
            )}
            {state && state.problems.length > 0 && (
                <ul className={styles.lines} aria-label="Regressioni">
                    {state.problems.map((problem) => (
                        <li key={problem} className={styles.error}>
                            {problem}
                        </li>
                    ))}
                </ul>
            )}
            {failed.length > 0 && (
                <ul className={styles.lines} aria-label="Casi non superati">
                    {failed.map((item) => (
                        <li key={item.id}>
                            <span className={styles.mono}>{item.id}</span>
                            {item.critical && (
                                <span className={styles.badge} data-tone="bad">
                                    critico
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
    const [confirming, setConfirming] = useState(false);
    const [rotated, setRotated] = useState<{ key: string; sessions_closed: number } | null>(null);
    const [error, setError] = useState<string | null>(null);

    const rotate = async () => {
        setConfirming(false);
        setError(null);
        try {
            setRotated(await postJson<{ key: string; sessions_closed: number }>("/api/system/access-key/rotate", { confirm: true }));
        } catch (err) {
            setError(message(err));
        }
    };

    if (!view.access_key.can_rotate) {
        return (
            <div className={styles.card}>
                <p className={styles.muted}>
                    Qui la chiave viene dall&apos;ambiente (<span className={styles.mono}>AEHUB_SECRET_KEY</span>): si cambia dove è
                    impostata, poi si riavvia. Nell&apos;app desktop si cambia da qui.
                </p>
            </div>
        );
    }

    return (
        <div className={styles.card}>
            <p className={styles.muted}>
                La chiave serve per entrare da un browser; l&apos;app desktop non la usa. Cambiandola, tutte le altre sessioni
                vengono chiuse; questa resta aperta.
            </p>
            {rotated ? (
                <div className={`${styles.card} ${styles.amber}`} role="status">
                    <p>Nuova chiave, la vedi solo adesso: copiala in un posto sicuro.</p>
                    <pre className={styles.pre} data-testid="new-key">
                        {rotated.key}
                    </pre>
                    <p className={styles.muted}>Sessioni chiuse: {rotated.sessions_closed}.</p>
                </div>
            ) : confirming ? (
                <div className={styles.row}>
                    <span className={styles.warn}>Chiudere tutte le altre sessioni e cambiare la chiave?</span>
                    <button type="button" className={`${styles.btn} ${styles.danger}`} onClick={() => void rotate()}>
                        Conferma: cambia la chiave
                    </button>
                    <button type="button" className={styles.linkBtn} onClick={() => setConfirming(false)}>
                        Annulla
                    </button>
                </div>
            ) : (
                <div className={styles.row}>
                    <button type="button" className={styles.btn} onClick={() => setConfirming(true)}>
                        Cambia la chiave
                    </button>
                </div>
            )}
            {error && <p className={styles.error}>{error}</p>}
        </div>
    );
}

function Logs() {
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
                <p className={styles.muted}>Avvisi ed errori del backend dall&apos;ultimo avvio, i più recenti per primi.</p>
                <button type="button" className={styles.linkBtn} onClick={() => void load()}>
                    Aggiorna
                </button>
            </div>
            {error && <p className={styles.error}>{error}</p>}
            {logs && logs.length === 0 && <p className={styles.muted}>Nessun avviso.</p>}
            {logs && logs.length > 0 && (
                <ul className={styles.lines} aria-label="Avvisi ed errori">
                    {logs.map((entry, index) => (
                        <li key={`${entry.at}-${index}`} className={entry.level === "warning" ? styles.warn : styles.error}>
                            <span className={styles.mono}>
                                {localTime(entry.at)} · {entry.logger}
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
                <h1 className={styles.title}>SISTEMA</h1>
                <button type="button" className={styles.linkBtn} onClick={() => void load()}>
                    Aggiorna
                </button>
            </div>

            {error && <p className={styles.error}>Sistema non disponibile: {error}</p>}
            {!view && !error && <p className={styles.muted}>Leggo lo stato…</p>}

            {view && (
                <div className={styles.stack}>
                    <Section id="state-title" title="STATO">
                        <StatusCards view={view} />
                    </Section>
                    <Section id="memory-title" title="MEMORIA">
                        <Memory view={view} />
                    </Section>
                    <Section id="updates-title" title="AGGIORNAMENTI">
                        <Updates view={view} />
                    </Section>
                    <Section id="recorder-title" title="FLIGHT RECORDER">
                        <Recorder />
                    </Section>
                    <Section id="evals-title" title="EVAL">
                        <Evals />
                    </Section>
                    <Section id="key-title" title="CHIAVE DI ACCESSO">
                        <AccessKey view={view} />
                    </Section>
                    <Section id="logs-title" title="AVVISI">
                        <Logs />
                    </Section>
                    <Section id="startup-title" title="PARAMETRI DI AVVIO">
                        <Startup view={view} />
                    </Section>
                </div>
            )}
        </main>
    );
}
