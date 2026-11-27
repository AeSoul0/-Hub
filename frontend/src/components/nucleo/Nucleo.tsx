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
 * N1 (ADR-040): commands go with delivery=live. While the model writes, the
 * draft of the answer shows in the conversation (answer.delta, marked as
 * being checked) and is replaced by the accepted answer; the answer is then
 * spoken sentence by sentence, the next one synthesized while one plays.
 *
 * N2 (ADR-041): with a wake word chosen, the page listens for it (in the
 * browser, wakeListener.ts) and, once heard, records the command until the
 * speaker stops, as if the microphone had been pressed. Listening pauses
 * while a command is recorded, sent or spoken.
 *
 * F2: the right pane also shows the runs of this session with their totals
 * against the limits and their timeline; a run, or all of them, stops from
 * here (POST /api/runs/{id}/cancel, /api/runs/stop-all, /api/runs/resume).
 */
"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useReducer, useRef, useState } from "react";

import type { ApprovalRequest, Decision } from "@/components/control-plane/ApprovalCard";
import CitedText from "@/components/control-plane/CitedText";
import { fetchApi, getJson, postJson } from "@/lib/api/client";
import { useWorkspaceEvents } from "@/lib/api/events";
import { chime, playReply, startRecording, type Recording } from "@/lib/nucleo/audio";
import {
    initialNucleo,
    MODE_LABELS,
    commandMoons,
    modeDetail,
    nucleoReducer,
    orbMode,
    resumedReply,
    roleName,
    toEngineEvent,
} from "@/lib/nucleo/engine";
import { IMPLEMENTER_ROLES } from "@/lib/nucleo/models";
import {
    currentConversation,
    keepLine,
    keepNucleo,
    liveCommands,
    newCommandId,
    recallNucleo,
    rememberConversation,
    type ChatLine,
} from "@/lib/nucleo/keep";
import { initialRuns, liveCount, runsReducer, type LiveView } from "@/lib/nucleo/runs";
import { resumedByVoice, speakInSentences, splitSentences, type SpokenPiece } from "@/lib/nucleo/voice";
import { startWakeListener, type WakeListener, type WakeStatus } from "@/lib/nucleo/wakeListener";
import { askNotifyPermissionOnce, notifyNow } from "@/lib/notify";
import { catalog, useInterface, useLanguage } from "@/lib/i18n";

import ApprovalPrompt from "./ApprovalPrompt";
import HistoryPanel, { conversationPath, type ConversationTurn } from "./HistoryPanel";
import Orb from "./Orb";
import RunsPanel from "./RunsPanel";
import SidePane from "./SidePane";
import styles from "./nucleo.module.css";


interface Reply {
    heard?: string;
    transcription?: string;
    audio_base64?: string;
    audio_mime?: string;
    // Set when the command ran at once, without the engine (ADR-035).
    instant?: { tool: string; ms: number; success: boolean };
    // "sentences": no audio here, the Nucleo speaks the answer piece by piece (N1).
    speak?: "sentences";
    // The run was stopped (by you, the global stop, a limit or the budget): a system line.
    stopped?: string;
}

interface Budget {
    month_spent: number | null;
    monthly_budget: number;
}

const TEXT = catalog({
    en: {
        denied: "denied · the call does not start",
        allowed: "allowed",
        commandFailed: "The command did not start:",
        stillWorking: "The connection was cut, but ÆHub is still working: the answer will appear here.",
        reminder: "⏰ Reminder:",
        instant: "instant",
        draft: "draft · being checked",
        micUnavailable: "Microphone not available:",
        micMissing: "The microphone is not available in this browser.",
        nothingHeard: "I heard nothing: try again closer to the microphone.",
        voiceFailed: "The voice did not arrive:",
        decisionFailed: "Decision not recorded:",
        stopFailed: "The run did not stop:",
        halted: "Engine stopped: the running runs stop and new ones are refused until you resume.",
        stopAllFailed: "Stop failed:",
        resumeFailed: "The engine does not restart:",
        panels: "Panels",
        conversation: "CONVERSATION",
        engine: "ENGINE",
        engineChip: "engine",
        online: "online",
        offline: "offline",
        activeRuns: "active runs",
        haltedButton: "ENGINE STOPPED · RESUME",
        confirmStop: "SURE? STOP EVERYTHING",
        stopAll: "STOP EVERYTHING",
        month: "month",
        conversationTitle: "Conversation",
        conversationView: "Conversation view",
        chatTab: "CONVERSATION",
        historyTab: "HISTORY",
        openFailed: "The conversation did not open:",
        emptyChat: "Your commands and the answers appear here.",
        me: "You",
        system: "System",
        channels: { voice: "voice", text: "text" },
        engineTitle: "Engine",
        engineView: "Engine view",
        events: "EVENTS",
        runs: "RUNS",
        emptyLog: "Run events appear here while the engine works.",
        sendVoice: "Stop and send the voice",
        speak: "Speak",
        roleLabel: "Role of the command",
        roleTitle: "Who works on the command: auto lets the triage choose",
        command: "Command",
        placeholder: "Type a command…",
        send: "SEND",
        hint: "SPACE to speak · drag the edge of the panels to make them taller",
        wake: {
            loading: (word: string) => `Wake word: loading «${word}»…`,
            listening: (word: string) => `Listening for «${word}»`,
            paused: (word: string) => `«${word}» paused while I listen or answer`,
            blocked: (word: string) => `Touch the page to start listening for «${word}»`,
            error: (word: string, detail: string) => `«${word}» not available: ${detail}`,
            speak: "speak now · it ends when you stop",
        },
    },
    it: {
        denied: "negata · la chiamata non parte",
        allowed: "consentita",
        commandFailed: "Il comando non è partito:",
        stillWorking: "La connessione si è interrotta, ma ÆHub sta ancora lavorando: la risposta arriverà qui.",
        reminder: "⏰ Promemoria:",
        instant: "istantaneo",
        draft: "bozza · in verifica",
        micUnavailable: "Microfono non disponibile:",
        micMissing: "Il microfono non è disponibile in questo browser.",
        nothingHeard: "Non ho sentito niente: riprova più vicino al microfono.",
        voiceFailed: "La voce non è arrivata:",
        decisionFailed: "Decisione non registrata:",
        stopFailed: "La run non si è fermata:",
        halted: "Motore fermato: le run in corso si fermano e le nuove sono rifiutate finché non riprendi.",
        stopAllFailed: "Stop non riuscito:",
        resumeFailed: "Il motore non riparte:",
        panels: "Pannelli",
        conversation: "CONVERSAZIONE",
        engine: "MOTORE",
        engineChip: "motore",
        online: "in linea",
        offline: "offline",
        activeRuns: "run attive",
        haltedButton: "MOTORE FERMO · RIPRENDI",
        confirmStop: "CONFERMI? FERMA TUTTO",
        stopAll: "FERMA TUTTO",
        month: "mese",
        conversationTitle: "Conversazione",
        conversationView: "Vista della conversazione",
        chatTab: "CONVERSAZIONE",
        historyTab: "CRONOLOGIA",
        openFailed: "La conversazione non si è aperta:",
        emptyChat: "Qui compaiono i tuoi comandi e le risposte.",
        me: "Tu",
        system: "Sistema",
        channels: { voice: "voce", text: "testo" },
        engineTitle: "Motore",
        engineView: "Vista del motore",
        events: "EVENTI",
        runs: "RUN",
        emptyLog: "Gli eventi delle run compaiono qui mentre il motore lavora.",
        sendVoice: "Ferma e invia la voce",
        speak: "Parla",
        roleLabel: "Ruolo del comando",
        roleTitle: "Chi lavora sul comando: automatico lascia scegliere il triage",
        command: "Comando",
        placeholder: "Scrivi un comando…",
        send: "INVIA",
        hint: "SPAZIO per parlare · trascina il bordo dei pannelli per allungarli",
        wake: {
            loading: (word: string) => `Parola di attivazione: carico «${word}»…`,
            listening: (word: string) => `In ascolto di «${word}»`,
            paused: (word: string) => `«${word}» in pausa mentre ascolto o rispondo`,
            blocked: (word: string) => `Tocca la pagina per ascoltare «${word}»`,
            error: (word: string, detail: string) => `«${word}» non disponibile: ${detail}`,
            speak: "parla ora · finisce quando smetti",
        },
    },
});

const errorOf = (error: unknown) => (error instanceof Error ? error.message : String(error));

const silence = () => 0;
const CHAT_LIMIT = 100;
// A burst of run events reads the live runs once.
const LIVE_REFRESH_MS = 300;
// The second click on "stop all" must come within this time.
const CONFIRM_MS = 4000;
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
    const lang = useLanguage();
    const t = TEXT[lang];
    // The event handlers read the language of the moment, not of their first render.
    const langRef = useRef(lang);
    useEffect(() => {
        langRef.current = lang;
    }, [lang]);
    // Back from another page: what was here is here again (keep.ts).
    const [state, dispatch] = useReducer(nucleoReducer, initialNucleo, (initial) => recallNucleo()?.nucleo ?? initial);
    const [chat, setChat] = useState<ChatLine[]>(() => recallNucleo()?.chat ?? []);
    const [showChat, setShowChat] = useState(true);
    const [showEvents, setShowEvents] = useState(true);
    const [listening, setListening] = useState(false);
    const [speaking, setSpeaking] = useState(false);
    // Commands sent and not answered yet: more can be sent meanwhile.
    const [inFlight, setInFlight] = useState(() => liveCommands.size);
    const sending = inFlight > 0;
    const [text, setText] = useState("");
    // The answer of each command while the model writes it (N1), by command id.
    const [drafts, setDrafts] = useState<Record<string, string>>({});
    // Whether this page is on screen: a reply that comes after it was left
    // goes to the memory, for when you come back.
    const mounted = useRef(false);
    // A newer answer stops the voice of the older one.
    const voiceTurn = useRef(0);
    // The worker role for the next commands; "" lets triage pick (F8).
    const [role, setRole] = useState("");
    const [now, setNow] = useState(() => Date.now());
    const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
    const [deciding, setDeciding] = useState(false);
    const [budget, setBudget] = useState<Budget | null>(null);
    const [spark, setSpark] = useState({ count: 0, amber: false });
    const [runs, runsDispatch] = useReducer(runsReducer, initialRuns, (initial) => recallNucleo()?.runs ?? initial);
    const [rightTab, setRightTab] = useState<"events" | "runs">(() => recallNucleo()?.tab ?? "events");
    // N6: the conversation the next command goes on in, and the tab on the left.
    const [conversation, setConversation] = useState(currentConversation);
    const [leftTab, setLeftTab] = useState<"chat" | "history">(() => recallNucleo()?.leftTab ?? "chat");
    const [confirmStop, setConfirmStop] = useState(false);
    const liveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    // The wake word (N2): only with the voice on and a word chosen.
    const iface = useInterface();
    const wake = iface?.voice.enabled && iface.wake && iface.wake.word !== "off" ? iface.wake : null;
    const wakeWord = wake?.word ?? "";
    const wakeThreshold = wake?.threshold ?? 0;
    const [wakeStatus, setWakeStatus] = useState<{ status: WakeStatus; detail: string } | null>(null);
    const wakeListener = useRef<WakeListener | null>(null);
    // The recording was started by the word: it ends by itself.
    const [byWordNow, setByWordNow] = useState(false);

    const level = useRef<() => number>(silence);
    const recording = useRef<Recording | null>(null);
    const chatId = useRef(chat.reduce((top, entry) => Math.max(top, entry.id), 0));
    const top = useRef<HTMLElement>(null);
    const draftLength = Object.values(drafts).reduce((total, text) => total + text.length, 0);
    const chatList = useStickToBottom(`${chat.length}:${draftLength}`);
    const logList = useStickToBottom(state.log.length);

    // What is on screen is kept for when you come back from another page.
    useEffect(() => {
        keepNucleo({ nucleo: state, chat, runs, tab: rightTab, leftTab });
    }, [state, chat, runs, rightTab, leftTab]);

    useEffect(() => {
        mounted.current = true;
        return () => {
            mounted.current = false;
            // Their requests answer to a page that is gone: the ends come as events.
            for (const command of liveCommands.values()) {
                command.adrift = true;
            }
        };
    }, []);

    /** A command answered (or failed): false when its end was already shown. */
    const finish = useCallback((id: string) => {
        if (!liveCommands.delete(id)) {
            return false;
        }
        setInFlight(liveCommands.size);
        setDrafts((current) => {
            const next = { ...current };
            delete next[id];
            return next;
        });
        return true;
    }, []);

    const say = useCallback((who: ChatLine["who"], line: string, channel?: ChatLine["channel"], note?: string) => {
        chatId.current += 1;
        const entry = { id: chatId.current, who, text: line, channel, note };
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

    // The answer spoken sentence by sentence (N1): the first sound comes after
    // one sentence, not the whole reply.
    const speakText = useCallback(async (reply: string) => {
        const turn = ++voiceTurn.current;
        const pieces = splitSentences(reply);
        if (!pieces.length) {
            return;
        }
        setSpeaking(true);
        try {
            await speakInSentences(
                pieces,
                (piece) =>
                    postJson<SpokenPiece>("/api/voice/speak", { text: piece, reply_chars: reply.length }).catch(() => null),
                (audio) =>
                    playReply(audio, (meter) => {
                        level.current = meter;
                    }).catch(() => undefined),
                () => voiceTurn.current === turn,
            );
        } finally {
            if (voiceTurn.current === turn) {
                setSpeaking(false);
            }
        }
    }, []);

    const handleReply = useCallback(
        async (reply: Reply) => {
            if (reply.stopped) {
                say("system", reply.stopped);
                return;
            }
            if (reply.transcription) {
                const note = reply.instant ? `${t.instant} · ${reply.instant.ms} ms` : undefined;
                say("aehub", reply.transcription, undefined, note);
            }
            if (reply.speak === "sentences" && reply.transcription) {
                await speakText(reply.transcription);
            } else if (reply.audio_base64) {
                await playAudio(reply.audio_base64);
            }
        },
        [say, playAudio, speakText, t.instant],
    );

    // A run asked by voice answers by voice also when it resumes after an
    // approval (F3). Best effort: the written reply is already in the chat.
    const speakResumed = speakText;

    const connection = useWorkspaceEvents(
        [
            "engine.event",
            "run.state",
            "approval.requested",
            "approval.decided",
            "run.resumed",
            "answer.delta",
            "answer.reset",
            "answer.final",
            "answer.failed",
            "reminder.due",
        ],
        (event) => {
            if (event.type === "reminder.due") {
                const text = String(event.data.text ?? "");
                say("system", `${TEXT[langRef.current].reminder} ${text}`);
                notifyNow("ÆHub", text);
                void chime();
                return;
            }
            const commandId = String(event.data.command_id ?? "");
            if (event.type === "answer.final" || event.type === "answer.failed") {
                // Only for a command whose request no longer brings the answer.
                if (liveCommands.get(commandId)?.adrift && finish(commandId)) {
                    if (event.type === "answer.final") {
                        if (typeof event.data.heard === "string" && event.data.heard) {
                            say("me", event.data.heard, "voice");
                        }
                        void handleReply(event.data.reply as Reply);
                    } else {
                        say("system", `${TEXT[langRef.current].commandFailed} ${String(event.data.detail ?? "")}`);
                    }
                }
                return;
            }
            if (event.type === "answer.delta") {
                if (liveCommands.has(commandId)) {
                    setDrafts((current) => ({ ...current, [commandId]: String(event.data.text ?? "") }));
                }
                return;
            }
            if (event.type === "answer.reset") {
                setDrafts((current) => {
                    const next = { ...current };
                    delete next[commandId];
                    return next;
                });
                return;
            }

            const engineEvent = toEngineEvent(event);
            if (engineEvent) {
                const at = Date.now();
                dispatch({ type: "engine", event: engineEvent, now: at, lang: langRef.current });
                runsDispatch({ type: "event", event: engineEvent, now: at, lang: langRef.current });
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
                        detail: denied ? TEXT[langRef.current].denied : TEXT[langRef.current].allowed,
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

    /** A new command, answered by its request or, when that is cut, by its events. */
    const startCommand = () => {
        const id = newCommandId();
        liveCommands.set(id, { adrift: false });
        setInFlight(liveCommands.size);
        return id;
    };

    /** A gateway cut the request (GitHub's port forwarding, after about a minute): wait for the events. */
    const cutByProxy = (id: string, response: Response) => {
        if (response.status !== 502 && response.status !== 504) {
            return false;
        }
        const command = liveCommands.get(id);
        if (command) {
            command.adrift = true;
            say("system", t.stillWorking);
        }
        return true;
    };

    /** The reply of a command, here or, when the page was left, in the memory. */
    const deliver = async (id: string, reply: Reply, heard?: string) => {
        if (!finish(id)) {
            return;
        }
        if (!mounted.current) {
            if (heard) {
                keepLine({ who: "me", text: heard, channel: "voice" });
            }
            if (reply.stopped || reply.transcription) {
                keepLine({ who: reply.stopped ? "system" : "aehub", text: reply.stopped || reply.transcription || "" });
            }
            return;
        }
        if (heard) {
            say("me", heard, "voice");
        }
        await handleReply(reply);
    };

    const failed = (id: string, line: string) => {
        if (!finish(id)) {
            return;
        }
        if (mounted.current) {
            say("system", line);
        } else {
            keepLine({ who: "system", text: line });
        }
    };

    const send = async (command: string) => {
        // The first command is a click: the moment to ask for notifications (ADR-037).
        askNotifyPermissionOnce();
        say("me", command, "text");
        const id = startCommand();
        const form = new FormData();
        form.append("text", command);
        form.append("delivery", "live");
        form.append("command_id", id);
        form.append("conversation", conversation);
        rememberConversation(conversation);
        if (role) {
            form.append("role", role);
        }
        try {
            const response = await fetchApi("/api/orchestrator/ask", { method: "POST", body: form });
            if (cutByProxy(id, response)) {
                return;
            }
            if (!response.ok) {
                throw new Error(await detailOf(response));
            }
            await deliver(id, await response.json());
        } catch (error) {
            failed(id, `${t.commandFailed} ${errorOf(error)}`);
        }
    };

    // `byWord`: started by the wake word, so it ends by itself when the speaker stops.
    const toggleMic = async (byWord = false) => {
        if (!listening) {
            askNotifyPermissionOnce();
            try {
                const started = await startRecording(
                    t.micMissing,
                    byWord ? { onEnd: () => void toggleRef.current() } : {},
                );
                recording.current = started;
                level.current = started.level;
                setByWordNow(byWord);
                setListening(true);
            } catch (error) {
                say("system", `${t.micUnavailable} ${errorOf(error)}`);
                wakeListener.current?.resume();
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

        const id = startCommand();
        try {
            const audio = await current.stop();
            const form = new FormData();
            form.append("file", audio, "voice.webm");
            form.append("delivery", "live");
            form.append("command_id", id);
            form.append("conversation", conversation);
            rememberConversation(conversation);
            const response = await fetchApi("/api/orchestrator/listen", { method: "POST", body: form });
            if (cutByProxy(id, response)) {
                return;
            }
            if (!response.ok) {
                throw new Error(await detailOf(response));
            }
            const reply: Reply = await response.json();
            if (!reply.heard) {
                failed(id, t.nothingHeard);
                return;
            }
            await deliver(id, reply, reply.heard);
        } catch (error) {
            failed(id, `${t.voiceFailed} ${errorOf(error)}`);
        }
    };

    /** Go on in a past conversation: its turns come back on screen (N6). */
    const openConversation = async (id: string) => {
        try {
            const view = await getJson<{ turns: ConversationTurn[] }>(conversationPath(id));
            const lines: ChatLine[] = [];
            for (const turn of view.turns) {
                lines.push({ id: lines.length + 1, who: "me", text: turn.task, channel: turn.channel });
                if (turn.answer) {
                    lines.push({ id: lines.length + 1, who: turn.status === "completed" ? "aehub" : "system", text: turn.answer });
                }
            }
            const kept = lines.slice(-CHAT_LIMIT);
            chatId.current = lines.length;
            setChat(kept);
            setConversation(id);
            rememberConversation(id);
            setLeftTab("chat");
        } catch (error) {
            say("system", `${t.openFailed} ${errorOf(error)}`);
            setLeftTab("chat");
        }
    };

    const newConversation = () => {
        const id = newCommandId();
        setChat([]);
        setConversation(id);
        rememberConversation(id);
        setLeftTab("chat");
    };

    const decide = async (id: string, decision: Decision) => {
        setDeciding(true);
        try {
            await postJson(`/api/approvals/${encodeURIComponent(id)}`, { decision });
        } catch (error) {
            say("system", `${t.decisionFailed} ${errorOf(error)}`);
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
            say("system", `${t.stopFailed} ${errorOf(error)}`);
        } finally {
            void refreshLive();
        }
    };

    const stopAll = async () => {
        setConfirmStop(false);
        try {
            await postJson("/api/runs/stop-all", {});
            runsDispatch({ type: "halt", halted: true });
            say("system", t.halted);
        } catch (error) {
            say("system", `${t.stopAllFailed} ${errorOf(error)}`);
        } finally {
            void refreshLive();
        }
    };

    const resumeAll = async () => {
        try {
            await postJson("/api/runs/resume", {});
            runsDispatch({ type: "halt", halted: false });
        } catch (error) {
            say("system", `${t.resumeFailed} ${errorOf(error)}`);
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

    // The word was heard: a short tone, then the command, as with the button.
    const busyRef = useRef(false);
    const onWake = useCallback(async () => {
        if (busyRef.current) {
            wakeListener.current?.resume();
            return;
        }
        await chime();
        await toggleRef.current(true);
    }, []);

    useEffect(() => {
        if (!wakeWord) {
            return;
        }
        let cancelled = false;
        let listener: WakeListener | null = null;
        startWakeListener({
            word: wakeWord,
            threshold: wakeThreshold,
            onWake: () => void onWake(),
            onStatus: (status, detail) => {
                if (!cancelled) {
                    setWakeStatus({ status, detail: detail ?? "" });
                }
            },
        }).then(
            (started) => {
                if (cancelled) {
                    started.stop();
                    return;
                }
                listener = started;
                wakeListener.current = started;
                if (busyRef.current) {
                    started.pause();
                }
            },
            (error) => {
                if (!cancelled) {
                    setWakeStatus({ status: "error", detail: errorOf(error) });
                }
            },
        );
        return () => {
            cancelled = true;
            listener?.stop();
            wakeListener.current = null;
            setWakeStatus(null);
        };
    }, [wakeWord, wakeThreshold, onWake]);

    const mode = orbMode(state, { listening, speaking, sending }, now);
    // Only recording blocks a new command: more can be sent while others run.
    const busy = listening;

    // Not while a command is recorded, sent or spoken: the reply must not wake it.
    const voiceBusy = busy || sending || speaking;
    useEffect(() => {
        busyRef.current = voiceBusy;
        if (voiceBusy) {
            wakeListener.current?.pause();
        } else {
            wakeListener.current?.resume();
        }
    }, [voiceBusy]);
    const appClass = [styles.app, showChat ? "" : styles.noLeft, showEvents ? "" : styles.noRight].join(" ");
    const spent = budget?.month_spent;
    const running = Math.max(state.activeRuns.length, liveCount(runs));
    // Commands running together: one moon each, next to the subagents' moons.
    const commandsRunning = runs.runs.filter(
        (run) => !run.parentId && (run.status === "running" || run.status === "waiting" || run.status === "cancelling"),
    );
    const orbMoons = [...commandMoons(commandsRunning), ...state.moons];

    return (
        <div className={appClass}>
            <header ref={top} className={styles.top}>
                <div className={styles.mark}>
                    ÆHUB<small>NUCLEO</small>
                </div>
                <div className={styles.toggles} role="group" aria-label={t.panels}>
                    <button
                        type="button"
                        className={styles.toggle}
                        aria-pressed={showChat}
                        aria-controls="nucleo-chat"
                        onClick={() => setShowChat((value) => !value)}
                    >
                        {t.conversation}
                    </button>
                    <button
                        type="button"
                        className={styles.toggle}
                        aria-pressed={showEvents}
                        aria-controls="nucleo-events"
                        onClick={() => setShowEvents((value) => !value)}
                    >
                        {t.engine}
                    </button>
                </div>
                <div className={styles.chips}>
                    <span className={styles.chip}>
                        <span className={styles.dot} data-state={connection} aria-hidden="true" />
                        {t.engineChip} <b>{connection === "live" ? t.online : connection === "offline" ? t.offline : "…"}</b>
                    </span>
                    <span className={styles.chip}>
                        {t.activeRuns} <b>{running}</b>
                    </span>
                    {runs.halted ? (
                        <button type="button" className={`${styles.toggle} ${styles.halted}`} onClick={() => void resumeAll()}>
                            {t.haltedButton}
                        </button>
                    ) : (
                        running > 0 && (
                            <button
                                type="button"
                                className={`${styles.toggle} ${styles.danger}`}
                                onClick={() => (confirmStop ? void stopAll() : setConfirmStop(true))}
                            >
                                {confirmStop ? t.confirmStop : t.stopAll}
                            </button>
                        )
                    )}
                    {budget && spent != null && (
                        <span className={styles.chip}>
                            {t.month} <b>${spent.toFixed(2)}</b> / ${budget.monthly_budget.toFixed(2)}
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

            <SidePane
                id="nucleo-chat"
                side="left"
                title={t.conversationTitle}
                count={chat.length}
                hidden={!showChat}
                ceiling={top}
                header={
                    <div className={`${styles.paneTitle} ${styles.tabs}`} role="group" aria-label={t.conversationView}>
                        <button type="button" aria-pressed={leftTab === "chat"} onClick={() => setLeftTab("chat")}>
                            {t.chatTab} <span>{chat.length || ""}</span>
                        </button>
                        <button type="button" aria-pressed={leftTab === "history"} onClick={() => setLeftTab("history")}>
                            {t.historyTab}
                        </button>
                    </div>
                }
            >
                {leftTab === "history" ? (
                    <HistoryPanel
                        current={conversation}
                        busy={sending}
                        onOpen={(id) => void openConversation(id)}
                        onNew={newConversation}
                    />
                ) : (
                <ol className={styles.stream} ref={chatList}>
                    {chat.length === 0 && draftLength === 0 ? (
                        <li className={styles.empty}>{t.emptyChat}</li>
                    ) : (
                        chat.map((line) => (
                            <li key={line.id} className={`${styles.msg} ${line.who === "me" ? styles.me : line.who === "system" ? styles.system : ""} rise`}>
                                <span className={styles.who}>
                                    {line.who === "me" ? t.me : line.who === "system" ? t.system : "ÆHub"}
                                    {line.channel ? ` · ${t.channels[line.channel]}` : ""}
                                    {line.note ? ` · ${line.note}` : ""}
                                </span>
                                <p>{line.who === "aehub" ? <CitedText text={line.text} /> : line.text}</p>
                            </li>
                        ))
                    )}
                    {Object.entries(drafts)
                        .filter(([, text]) => text)
                        .map(([id, text]) => (
                            <li key={id} className={`${styles.msg} ${styles.draft}`} aria-live="polite" data-testid="answer-draft">
                                <span className={styles.who}>ÆHub · {t.draft}</span>
                                <p>{text}</p>
                            </li>
                        ))}
                </ol>
                )}
            </SidePane>

            <main className={styles.core}>
                <Orb mode={mode} moons={orbMoons} level={() => level.current()} spark={spark} />
                <span className={`${styles.tick} ${styles.tl}`} />
                <span className={`${styles.tick} ${styles.tr}`} />
                <span className={`${styles.tick} ${styles.bl}`} />
                <span className={`${styles.tick} ${styles.br}`} />
                <div className={styles.state} data-mode={mode} aria-live="polite">
                    <strong>{MODE_LABELS[lang][mode]}</strong>
                    <span>{listening && byWordNow ? t.wake.speak : modeDetail(mode, state, lang, commandsRunning.length)}</span>
                </div>
                <ApprovalPrompt pending={approvals} busy={deciding} onDecide={decide} />
            </main>

            <SidePane
                id="nucleo-events"
                side="right"
                title={t.engineTitle}
                count={state.log.length}
                hidden={!showEvents}
                ceiling={top}
                header={
                    <div className={`${styles.paneTitle} ${styles.tabs}`} role="group" aria-label={t.engineView}>
                        <button type="button" aria-pressed={rightTab === "events"} onClick={() => setRightTab("events")}>
                            {t.events} <span>{state.log.length || ""}</span>
                        </button>
                        <button type="button" aria-pressed={rightTab === "runs"} onClick={() => setRightTab("runs")}>
                            {t.runs} <span>{liveCount(runs) || ""}</span>
                        </button>
                    </div>
                }
            >
                {rightTab === "runs" ? (
                    <RunsPanel state={runs} onStop={(runId) => void stopRun(runId)} />
                ) : (
                    <ol className={styles.stream} ref={logList}>
                        {state.log.length === 0 ? (
                            <li className={styles.empty}>{t.emptyLog}</li>
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
                        aria-label={listening ? t.sendVoice : t.speak}
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
                        <select
                            aria-label={t.roleLabel}
                            title={t.roleTitle}
                            className={styles.role}
                            value={role}
                            onChange={(event) => setRole(event.target.value)}
                        >
                            <option value="">auto</option>
                            {IMPLEMENTER_ROLES.map((item) => (
                                <option key={item} value={item}>
                                    {roleName(item)}
                                </option>
                            ))}
                        </select>
                        <input
                            aria-label={t.command}
                            autoComplete="off"
                            placeholder={t.placeholder}
                            value={text}
                            onChange={(event) => setText(event.target.value)}
                        />
                        <button type="submit" disabled={busy || !text.trim()}>
                            {t.send}
                        </button>
                    </form>
                </div>
                {wake && wakeStatus && (
                    <div className={styles.wake} data-testid="wake-status" data-status={wakeStatus.status} role="status">
                        <span className={styles.wakeDot} aria-hidden="true" />
                        {wakeStatus.status === "error"
                            ? t.wake.error(wake.label, wakeStatus.detail)
                            : t.wake[wakeStatus.status](wake.label)}
                    </div>
                )}
                <div className={styles.hint}>{t.hint}</div>
            </footer>
        </div>
    );
}
