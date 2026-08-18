/**
 * @file frontend/src/components/layout/TerminalLog.tsx
 * @description Core module for A.U.R.O.R.A. System
 *
 * Implements primary logic and architectural constraints.
 *
 * Architectural constraints and responsibilities apply here.
 * Testability and dependency separation are enforced.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { Terminal } from "lucide-react";
import BentoWidget from "@/components/widgets/BentoWidget";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:3002";

interface LogEvent {
    id: string;
    type: string;
    data: any;
    timestamp: Date;
}

export default function TerminalLog() {
    const [logs, setLogs] = useState<LogEvent[]>([]);
    const endOfMessagesRef = useRef<HTMLDivElement>(null);
    const eventSourceRef = useRef<EventSource | null>(null);

    // Auto-scroll to bottom on new logs
    useEffect(() => {
        endOfMessagesRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [logs]);

    useEffect(() => {
        let sessionId = "default-session";
        if (typeof window !== "undefined") {
            sessionId = localStorage.getItem("aehub_session_id") || "";
            if (!sessionId) {
                sessionId =
                    typeof crypto !== "undefined" && crypto.randomUUID
                        ? crypto.randomUUID()
                        : Math.random().toString(36).substring(2, 15);
                localStorage.setItem("aehub_session_id", sessionId);
            }
        }

        const url = `${API_BASE_URL}/api/events?session_id=${sessionId}`;
        
        // Setup EventSource for SSE
        const eventSource = new EventSource(url, { withCredentials: true });
        eventSourceRef.current = eventSource;

        eventSource.onmessage = (event) => {
            try {
                const parsed = JSON.parse(event.data);
                const newLog: LogEvent = {
                    id: Math.random().toString(36).substring(2, 9),
                    type: parsed.type,
                    data: parsed.data,
                    timestamp: new Date()
                };
                setLogs(prev => [...prev, newLog]);
            } catch (err) {
                console.error("Failed to parse SSE message", err);
            }
        };

        eventSource.onerror = (err) => {
            console.warn("EventSource connection lost or failed. Reconnecting...");
            // Reconnection is handled automatically by EventSource.
            // We use console.warn instead of console.error to avoid Next.js dev overlay triggering.
        };

        return () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }
        };
    }, []);

    return (
        <BentoWidget title="SYS_LOG // TERMINAL" icon={Terminal} colorKey="cyan" colSpan={1} rowSpan={2}>
            <div className="relative flex flex-col h-full w-full mt-2 rounded-xl overflow-hidden bg-[#040914] border border-cyan-900/50 shadow-[inset_0_0_20px_rgba(6,182,212,0.02)]">
                {/* Header */}
                <div className="w-full bg-[#071120] border-b border-cyan-900/50 p-2 flex items-center justify-between text-[10px] font-mono text-cyan-500/70">
                    <span>LIVE_EVENT_STREAM</span>
                    <div className="flex items-center gap-2">
                        <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
                        </span>
                        <span>CONNECTED</span>
                    </div>
                </div>

                {/* Log View */}
                <div className="flex-1 overflow-y-auto p-3 font-mono text-[11px] space-y-2 custom-scrollbar">
                    {logs.length === 0 ? (
                        <div className="text-cyan-800/50 italic">Waiting for incoming telemetry...</div>
                    ) : (
                        logs.map((log) => (
                            <div key={log.id} className="flex gap-2">
                                <span className="text-cyan-600/50 shrink-0">
                                    [{log.timestamp.toLocaleTimeString("it-IT", { hour12: false })}]
                                </span>
                                <span className="text-cyan-400 font-bold shrink-0">
                                    {log.type.toUpperCase()}:
                                </span>
                                <span className="text-cyan-100 break-words">
                                    {typeof log.data === 'object' ? JSON.stringify(log.data) : String(log.data)}
                                </span>
                            </div>
                        ))
                    )}
                    <div ref={endOfMessagesRef} />
                </div>
            </div>
        </BentoWidget>
    );
}

