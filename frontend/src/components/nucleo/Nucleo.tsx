/**
 * @file frontend/src/components/nucleo/Nucleo.tsx
 * @description The home of ÆHub (F1): the sphere in the centre, the
 * conversation on the left, the engine's live events on the right.
 *
 * Everything the sphere does comes from the engine: `engine.event`,
 * `run.state` and the approval events on the workspace stream, plus what
 * the user is doing here (talking, sending, listening to the reply).
 * Commands go to the orchestrator: text to /api/orchestrator/ask, voice to
 * /api/orchestrator/listen (transcribed locally, ADR-021).
 *
 * F2: the right pane also shows the runs of this session with their totals
 * against the limits and their timeline; a run, or all of them, stops from
 * here (POST /api/runs/{id}/cancel, /api/runs/stop-all, /api/runs/resume).
 */
"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useReducer, useRef, useState } from "react";

import type { ApprovalRequest, Decision } from "@/components/control-plane/ApprovalCard";
import { fetchApi, getJson, postJson } from "@/lib/api/client";
import { useWorkspaceEvents } from "@/lib/api/events";
import { playReply, startRecording, type Recording } from "@/lib/nucleo/audio";
import {
    initialNucleo,
    MODE_LABELS,
    modeDetail,
    nucleoReducer,
    orbMode,
    resumedReply,
    toEngineEvent,
} from "@/lib/nucleo/engine";
import { initialRuns, liveCount, runsReducer, type LiveView } from "@/lib/nucleo/runs";
import { resumedByVoice } from "@/lib/nucleo/voice";

import ApprovalPrompt from "./ApprovalPrompt";
import Orb from "./Orb";
import RunsPanel from "./RunsPanel";
import SidePane from "./SidePane";
import styles from "./nucleo.module.css";

interface ChatLine {
    id: number;
    who: "me" | "aehub" | "system";
    text: string;
    channel?: "voce" | "testo";
}

interface Reply {
    heard?: string;
    transcription?: string;
    audio_base64?: string;
    audio_mime?: string;
}

interface Budget {
    month_spent: number | null;
    monthly_budget: number;
}

const silence = () => 0;
const CHAT_LIMIT = 100;
// A burst of run events reads the live runs once.
const LIVE_REFRESH_MS = 300;
// The second click on "stop all" must come within this time.
const CONFIRM_MS = 4000;
// The longest text POST /api/voice/speak accepts.
const SPEAK_LIMIT = 5000;

async function detailOf(response: Response): Promise<string> {
    try {
        const body = await response.json();
        if (typeof body?.detail === "string") {
            return body.detail;
        }
    } catch {
        // not JSON
    }
    return `HTTP ${response.status}`;
}

/** Keep a list scrolled to its newest line. */
function useStickToBottom(dependency: unknown) {
    const ref = useRef<HTMLOListElement>(null);
    useEffect(() => {
        if (ref.current) {
            ref.current.scrollTop = ref.current.scrollHeight;
        }
    }, [dependency]);
    return ref;
}

export default function Nucleo() {
    const [state, dispatch] = useReducer(nucleoReducer, initialNucleo);
    const [chat, setChat] = useState<ChatLine[]>([]);
    const [showChat, setShowChat] = useState(true);
    const [showEvents, setShowEvents] = useState(true);
    const [listening, setListening] = useState(false);
    const [speaking, setSpeaking] = useState(false);
    const [sending, setSending] = useState(false);
    const [text, setText] = useState("");
    const [now, setNow] = useState(() => Date.now());
    const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
    const [deciding, setDeciding] = useState(false);
    const [budget, setBudget] = useState<Budget | null>(null);
    const [spark, setSpark] = useState({ count: 0, amber: false });
    const [runs, runsDispatch] = useReducer(runsReducer, initialRuns);
    const [rightTab, setRightTab] = useState<"events" | "runs">("events");
    const [confirmStop, setConfirmStop] = useState(false);
    const liveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

    const level = useRef<() => number>(silence);
    const recording = useRef<Recording | null>(null);
    const chatId = useRef(0);
    const top = useRef<HTMLElement>(null);
    const chatList = useStickToBottom(chat.length);
    const logList = useStickToBottom(state.log.length);

    const say = useCallback((who: ChatLine["who"], line: string, channel?: ChatLine["channel"]) => {
        chatId.current += 1;
        const entry = { id: chatId.current, who, text: line, channel };
        setChat((current) => [...current.slice(-(CHAT_LIMIT - 1)), entry]);
    }, []);

    const refreshApprovals = useCallback(async () => {
        try {
            const pending = await getJson<ApprovalRequest[]>("/api/approvals");
            setApprovals(pending);
            dispatch({ type: "approvals", count: pending.length });
        } catch {
            // The stream reconnects and refreshes again.
        }
    }, []);

    const refreshBudget = useCallback(async () => {
        try {
            const stats = await getJson<{ budget: Budget }>("/api/runs/stats", { params: { days: 1 } });
            setBudget(stats.budget);
        } catch {
            // Optional: the chip just stays hidden.
        }
    }, []);

    const refreshLive = useCallback(async () => {
        try {
            const view = await getJson<LiveView>("/api/runs/live");
            runsDispatch({ type: "live", view, now: Date.now() });
        } catch {
            // The meters keep following the live events.
        }
    }, []);

    const refreshLiveSoon = useCallback(() => {
        if (liveTimer.current) {
            clearTimeout(liveTimer.current);
        }
        liveTimer.current = setTimeout(() => {
            liveTimer.current = null;
            void refreshLive();
        }, LIVE_REFRESH_MS);
    }, [refreshLive]);

    useEffect(
        () => () => {
            if (liveTimer.current) {
                clearTimeout(liveTimer.current);
            }
        },
        [],
    );

    const playAudio = useCallback(async (audioBase64: string) => {
        setSpeaking(true);
        try {
            await playReply(audioBase64, (meter) => {
                level.current = meter;
            });
        } catch {
            // The written reply is already there.
        } finally {
            setSpeaking(false);
        }
    }, []);

    // A run asked by voice answers by voice also when it resumes after an
    // approval (F3). Best effort: the written reply is already in the chat.
    const speakResumed = useCallback(
        async (reply: string) => {
            try {
                const spoken = await postJson<Reply>("/api/voice/speak", { text: reply.slice(0, SPEAK_LIMIT) });
                if (spoken.audio_base64) {
                    await playAudio(spoken.audio_base64);
                }
            } catch {
                // Voice off or unavailable: nothing to play.
            }
        },
        [playAudio],
    );

    const connection = useWorkspaceEvents(
        ["engine.event", "run.state", "approval.requested", "approval.decided", "run.resumed"],
        (event) => {
            const engineEvent = toEngineEvent(event);
            if (engineEvent) {
                const at = Date.now();
                dispatch({ type: "engine", event: engineEvent, now: at });
                runsDispatch({ type: "event", event: engineEvent, now: at });
                setNow(at);
                setSpark((current) => ({
                    count: current.count + 1,
                    amber: engineEvent.event_type === "tool.approval_required",
                }));
                if (engineEvent.event_type === "run.completed" || engineEvent.event_type === "model.called") {
                    void refreshBudget();
                }
                if (engineEvent.event_type === "run.started" || engineEvent.event_type === "subagent.spawned") {
                    refreshLiveSoon();
                }
                return;
            }

            if (event.type === "run.state") {
                const runId = String(event.data.run_id ?? "");
                const runState = String(event.data.state ?? "");
                dispatch({ type: "runState", runId, state: runState });
                runsDispatch({ type: "runState", runId, state: runState, now: Date.now() });
                refreshLiveSoon();
                return;
            }

            if (event.type === "approval.decided") {
                const denied = event.data.decision === "deny";
                dispatch({
                    type: "note",
                    line: {
                        at: new Date().toTimeString().slice(0, 8),
                        name: "approval.decided",
                        detail: denied ? "negata · la chiamata non parte" : "consentita",
                        kind: denied ? "deny" : "approval",
                    },
                });
            }

            if (event.type === "run.resumed") {
                const reply = resumedReply(event.data);
                if (reply) {
                    say("aehub", reply);
                    if (resumedByVoice(event.data)) {
                        void speakResumed(reply);
                    }
                } else if (typeof event.data.error === "string") {
                    say("system", event.data.error);
                }
            }

            void refreshApprovals();
        },
        () => {
            void refreshApprovals();
            void refreshBudget();
            void refreshLive();
        },
    );

    // "Stop all" asks for a second click, then forgets it.
    useEffect(() => {
        if (!confirmStop) {
            return;
        }
        const timer = setTimeout(() => setConfirmStop(false), CONFIRM_MS);
        return () => clearTimeout(timer);
    }, [confirmStop]);

    // The scan of a tool call fades on its own.
    useEffect(() => {
        if (state.toolUntil <= now) {
            return;
        }
        const timer = setTimeout(() => setNow(Date.now()), state.toolUntil - now + 20);
        return () => clearTimeout(timer);
    }, [state.toolUntil, now]);

    // Leaving the page closes the microphone.
    useEffect(() => () => recording.current?.cancel(), []);

    const handleReply = useCallback(
        async (reply: Reply) => {
            if (reply.transcription) {
                say("aehub", reply.transcription);
            }
            if (reply.audio_base64) {
                await playAudio(reply.audio_base64);
            }
        },
        [say, playAudio],
    );

    const send = async (command: string) => {
        setSending(true);
        say("me", command, "testo");
        const form = new FormData();
        form.append("text", command);
        try {
            const response = await fetchApi("/api/orchestrator/ask", { method: "POST", body: form });
            if (!response.ok) {
                throw new Error(await detailOf(response));
            }
            setSending(false);
            await handleReply(await response.json());
        } catch (error) {
            say("system", `Il comando non è partito: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
            setSending(false);
        }
    };

    const toggleMic = async () => {
        if (!listening) {
            try {
                const started = await startRecording();
                recording.current = started;
                level.current = started.level;
                setListening(true);
            } catch (error) {
                say("system", `Microfono non disponibile: ${error instanceof Error ? error.message : String(error)}`);
            }
            return;
        }

        const current = recording.current;
        recording.current = null;
        level.current = silence;
        setListening(false);
        if (!current) {
            return;
        }

        setSending(true);
        try {
            const audio = await current.stop();
            const form = new FormData();
            form.append("file", audio, "voce.webm");
            const response = await fetchApi("/api/orchestrator/listen", { method: "POST", body: form });
            if (!response.ok) {
                throw new Error(await detailOf(response));
            }
            const reply: Reply = await response.json();
            if (!reply.heard) {
                say("system", "Non ho sentito niente: riprova più vicino al microfono.");
                return;
            }
            say("me", reply.heard, "voce");
            setSending(false);
            await handleReply(reply);
        } catch (error) {
            say("system", `La voce non è arrivata: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
            setSending(false);
        }
    };

    const decide = async (id: string, decision: Decision) => {
        setDeciding(true);
        try {
            await postJson(`/api/approvals/${encodeURIComponent(id)}`, { decision });
        } catch (error) {
            say("system", `Decisione non registrata: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
            setDeciding(false);
            void refreshApprovals();
        }
    };

    const stopRun = async (runId: string) => {
        runsDispatch({ type: "cancelling", runId });
        try {
            await postJson(`/api/runs/${encodeURIComponent(runId)}/cancel`, {});
        } catch (error) {
            say("system", `La run non si è fermata: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
            void refreshLive();
        }
    };

    const stopAll = async () => {
        setConfirmStop(false);
        try {
            await postJson("/api/runs/stop-all", {});
            runsDispatch({ type: "halt", halted: true });
            say("system", "Motore fermato: le run in corso si fermano e le nuove sono rifiutate finché non riprendi.");
        } catch (error) {
            say("system", `Stop non riuscito: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
            void refreshLive();
        }
    };

    const resumeAll = async () => {
        try {
            await postJson("/api/runs/resume", {});
            runsDispatch({ type: "halt", halted: false });
        } catch (error) {
            say("system", `Il motore non riparte: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
            void refreshLive();
        }
    };

    // Space toggles the microphone when no field has the focus.
    const toggleRef = useRef(toggleMic);
    useEffect(() => {
        toggleRef.current = toggleMic;
    });
    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            const target = event.target as HTMLElement | null;
            if (event.code !== "Space" || event.repeat || target?.closest("input, textarea, select, button, [role=separator]")) {
                return;
            }
            event.preventDefault();
            void toggleRef.current();
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, []);

    const mode = orbMode(state, { listening, speaking, sending }, now);
    const busy = sending || listening;
    const appClass = [styles.app, showChat ? "" : styles.noLeft, showEvents ? "" : styles.noRight].join(" ");
    const spent = budget?.month_spent;
    const running = Math.max(state.activeRuns.length, liveCount(runs));

    return (
        <div className={appClass}>
            <header ref={top} className={styles.top}>
                <div className={styles.mark}>
                    ÆHUB<small>NUCLEO</small>
                </div>
                <div className={styles.toggles} role="group" aria-label="Pannelli">
                    <button
                        type="button"
                        className={styles.toggle}
                        aria-pressed={showChat}
                        aria-controls="nucleo-chat"
                        onClick={() => setShowChat((value) => !value)}
                    >
                        CONVERSAZIONE
                    </button>
                    <button
                        type="button"
                        className={styles.toggle}
                        aria-pressed={showEvents}
                        aria-controls="nucleo-events"
                        onClick={() => setShowEvents((value) => !value)}
                    >
                        MOTORE
                    </button>
                </div>
                <div className={styles.chips}>
                    <span className={styles.chip}>
                        <span className={styles.dot} data-state={connection} aria-hidden="true" />
                        motore <b>{connection === "live" ? "in linea" : connection === "offline" ? "offline" : "…"}</b>
                    </span>
                    <span className={styles.chip}>
                        run attive <b>{running}</b>
                    </span>
                    {runs.halted ? (
                        <button type="button" className={`${styles.toggle} ${styles.halted}`} onClick={() => void resumeAll()}>
                            MOTORE FERMO · RIPRENDI
                        </button>
                    ) : (
                        running > 0 && (
                            <button
                                type="button"
                                className={`${styles.toggle} ${styles.danger}`}
                                onClick={() => (confirmStop ? void stopAll() : setConfirmStop(true))}
                            >
                                {confirmStop ? "CONFERMI? FERMA TUTTO" : "FERMA TUTTO"}
                            </button>
                        )
                    )}
                    {budget && spent != null && (
                        <span className={styles.chip}>
                            mese <b>${spent.toFixed(2)}</b> / ${budget.monthly_budget.toFixed(2)}
                            <span className={styles.meter} aria-hidden="true">
                                <i style={{ width: `${Math.min(100, (spent / Math.max(budget.monthly_budget, 0.01)) * 100)}%` }} />
                            </span>
                        </span>
                    )}
                    <Link className={`${styles.chip} ${styles.link}`} href="/control-plane">
                        Control Plane
                    </Link>
                </div>
            </header>

            <SidePane id="nucleo-chat" side="left" title="Conversazione" count={chat.length} hidden={!showChat} ceiling={top}>
                <ol className={styles.stream} ref={chatList}>
                    {chat.length === 0 ? (
                        <li className={styles.empty}>Qui compaiono i tuoi comandi e le risposte.</li>
                    ) : (
                        chat.map((line) => (
                            <li key={line.id} className={`${styles.msg} ${line.who === "me" ? styles.me : line.who === "system" ? styles.system : ""} rise`}>
                                <span className={styles.who}>
                                    {line.who === "me" ? "Tu" : line.who === "system" ? "Sistema" : "ÆHub"}
                                    {line.channel ? ` · ${line.channel}` : ""}
                                </span>
                                <p>{line.text}</p>
                            </li>
                        ))
                    )}
                </ol>
            </SidePane>

            <main className={styles.core}>
                <Orb mode={mode} moons={state.moons} level={() => level.current()} spark={spark} />
                <span className={`${styles.tick} ${styles.tl}`} />
                <span className={`${styles.tick} ${styles.tr}`} />
                <span className={`${styles.tick} ${styles.bl}`} />
                <span className={`${styles.tick} ${styles.br}`} />
                <div className={styles.state} data-mode={mode} aria-live="polite">
                    <strong>{MODE_LABELS[mode]}</strong>
                    <span>{modeDetail(mode, state)}</span>
                </div>
                <ApprovalPrompt pending={approvals} busy={deciding} onDecide={decide} />
            </main>

            <SidePane
                id="nucleo-events"
                side="right"
                title="Motore"
                count={state.log.length}
                hidden={!showEvents}
                ceiling={top}
                header={
                    <div className={`${styles.paneTitle} ${styles.tabs}`} role="group" aria-label="Vista del motore">
                        <button type="button" aria-pressed={rightTab === "events"} onClick={() => setRightTab("events")}>
                            EVENTI <span>{state.log.length || ""}</span>
                        </button>
                        <button type="button" aria-pressed={rightTab === "runs"} onClick={() => setRightTab("runs")}>
                            RUN <span>{liveCount(runs) || ""}</span>
                        </button>
                    </div>
                }
            >
                {rightTab === "runs" ? (
                    <RunsPanel state={runs} onStop={(runId) => void stopRun(runId)} />
                ) : (
                    <ol className={styles.stream} ref={logList}>
                        {state.log.length === 0 ? (
                            <li className={styles.empty}>Gli eventi delle run compaiono qui mentre il motore lavora.</li>
                        ) : (
                            state.log.map((line) => (
                                <li key={line.id} className={`${styles.ev} rise`} data-k={line.kind}>
                                    <time>{line.at}</time>
                                    <div className={styles.evBody}>
                                        <span className={styles.evName}>{line.name}</span>
                                        {line.risk && (
                                            <span className={`${styles.risk} ${line.risk === "HIGH" ? styles.riskHigh : ""}`}>{line.risk}</span>
                                        )}
                                        {line.detail && <span className={styles.evDetail}>{line.detail}</span>}
                                    </div>
                                </li>
                            ))
                        )}
                    </ol>
                )}
            </SidePane>

            <footer className={styles.dock}>
                <div className={styles.bar}>
                    <button
                        type="button"
                        className={styles.mic}
                        aria-pressed={listening}
                        aria-label={listening ? "Ferma e invia la voce" : "Parla"}
                        disabled={sending}
                        onClick={() => void toggleMic()}
                    >
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <rect x="9" y="3" width="6" height="12" rx="3" />
                            <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
                        </svg>
                    </button>
                    <form
                        className={styles.ask}
                        onSubmit={(event) => {
                            event.preventDefault();
                            const command = text.trim();
                            if (command && !busy) {
                                setText("");
                                void send(command);
                            }
                        }}
                    >
                        <input
                            aria-label="Comando"
                            autoComplete="off"
                            placeholder="Scrivi un comando…"
                            value={text}
                            onChange={(event) => setText(event.target.value)}
                        />
                        <button type="submit" disabled={busy || !text.trim()}>
                            INVIA
                        </button>
                    </form>
                </div>
                <div className={styles.hint}>SPAZIO per parlare · trascina il bordo dei pannelli per allungarli</div>
            </footer>
        </div>
    );
}
