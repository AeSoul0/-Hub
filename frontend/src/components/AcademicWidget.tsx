"use client";

import { useEffect, useState } from "react";
import BentoWidget from "./BentoWidget";
import { GraduationCap, LogIn, RefreshCcw } from "lucide-react";

// ==============================================================================
// ENVIRONMENT & AUTHENTICATION CONFIGURATION
// ==============================================================================
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:3002";
const API_SECRET_KEY = process.env.NEXT_PUBLIC_AEHUB_KEY || "";

const getAuthHeaders = (): Record<string, string> => {
    let sessionId = "default-session";
    if (typeof window !== "undefined") {
        sessionId = localStorage.getItem("aehub_session_id") || "default-session";
    }
    return {
        "X-AeHub-Key": API_SECRET_KEY,
        "X-Session-ID": sessionId,
    };
};

type AcademicData = {
    gpa: number;
    exams: number;
    cfu: number;
};

const DEFAULT_DATA: AcademicData = { gpa: 0, exams: 0, cfu: 0 };

export default function AcademicWidget() {
    const [data, setData] = useState<AcademicData>(DEFAULT_DATA);
    const [loading, setLoading] = useState<boolean>(true);
    const [cookieInput, setCookieInput] = useState<string>("");
    const [isSyncing, setIsSyncing] = useState<boolean>(false);

    const loadAcademic = async () => {
        try {
            setLoading(true);
            const res = await fetch(`${API_BASE_URL}/api/academic/status`, {
                method: "GET",
                headers: getAuthHeaders(),
            });

            if (!res.ok) throw new Error(`HTTP Verification Failed: ${res.status}`);

            const json = await res.json();
            const d = json?.data;
            if (d) {
                setData({
                    gpa: typeof d.gpa === "number" ? d.gpa : 0,
                    exams: typeof d.exams === "number" ? d.exams : 0,
                    cfu: typeof d.cfu === "number" ? d.cfu : 0,
                });
            } else {
                setData(DEFAULT_DATA);
            }
        } catch (e: any) {
            console.error("Diagnostic Fetch Corrupted:", e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadAcademic();
    }, []);

    // ==============================================================================
    // HEADLESS SYNCHRONIZATION TRIGGER
    // ==============================================================================
    const handleSync = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!cookieInput) return;

        setIsSyncing(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/academic/login`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...getAuthHeaders(),
                },
                body: JSON.stringify({ cookie_string: cookieInput }),
            });

            if (res.ok) {
                setCookieInput("");
                // Polling simulation: Wait for backend headless extraction to complete
                setTimeout(() => {
                    loadAcademic();
                    setIsSyncing(false);
                }, 10000);
            } else {
                setIsSyncing(false);
            }
        } catch (err) {
            console.error(err);
            setIsSyncing(false);
        }
    };

    // ==============================================================================
    // HUD RENDERING SHELL
    // ==============================================================================
    const isAuthenticated = data.gpa > 0 || data.cfu > 0;

    return (
        <BentoWidget title="Academic_Sync" icon={GraduationCap} colorKey="emerald">
            <div className="flex flex-col h-full mt-2 justify-between">
                {loading ? (
                    <div className="flex-1 flex items-center justify-center">
                        <RefreshCcw className="w-5 h-5 text-emerald-500/50 animate-spin" />
                    </div>
                ) : !isAuthenticated ? (
                    // UNAUTHENTICATED STATE: Prompt for Raw Session Cookie
                    <form
                        onSubmit={handleSync}
                        className="flex flex-col gap-2 h-full justify-center"
                    >
                        <span className="text-[10px] font-mono text-emerald-600/70 dark:text-emerald-400/70 uppercase tracking-wider text-center">
                            Awaiting Session Auth
                        </span>
                        <input
                            type="password"
                            value={cookieInput}
                            onChange={(e) => setCookieInput(e.target.value)}
                            disabled={isSyncing}
                            placeholder="Paste InfoStud Cookie..."
                            className="w-full bg-slate-50 dark:bg-slate-900/40 border border-emerald-500/30 rounded-lg py-2 px-3 text-[11px] font-mono text-slate-800 dark:text-emerald-50 placeholder-slate-400 dark:placeholder-emerald-700/60 focus:outline-none focus:border-emerald-500 transition-all disabled:opacity-50"
                        />
                        <button
                            type="submit"
                            disabled={isSyncing || !cookieInput}
                            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 font-bold text-[10px] uppercase tracking-widest transition-colors disabled:opacity-50"
                        >
                            {isSyncing ? (
                                <>
                                    <RefreshCcw className="w-3 h-3 animate-spin" /> Syncing Node...
                                </>
                            ) : (
                                <>
                                    <LogIn className="w-3 h-3" /> Connect
                                </>
                            )}
                        </button>
                    </form>
                ) : (
                    // AUTHENTICATED STATE: Render Extracted Metrics
                    <div className="flex flex-col h-full justify-center gap-3">
                        <div className="grid grid-cols-2 gap-2">
                            <div className="bg-slate-50 dark:bg-emerald-950/20 border border-slate-100 dark:border-emerald-900/30 rounded-lg p-2 flex flex-col items-center justify-center">
                                <span className="text-[9px] uppercase tracking-widest text-slate-400 dark:text-emerald-500/60 font-bold">
                                    GPA Score
                                </span>
                                <span className="text-xl font-mono text-slate-700 dark:text-emerald-300">
                                    {data.gpa.toFixed(2)}
                                </span>
                            </div>
                            <div className="bg-slate-50 dark:bg-emerald-950/20 border border-slate-100 dark:border-emerald-900/30 rounded-lg p-2 flex flex-col items-center justify-center">
                                <span className="text-[9px] uppercase tracking-widest text-slate-400 dark:text-emerald-500/60 font-bold">
                                    Earned CFU
                                </span>
                                <span className="text-xl font-mono text-slate-700 dark:text-emerald-300">
                                    {data.cfu}
                                </span>
                            </div>
                        </div>
                        <div className="w-full bg-slate-50 dark:bg-emerald-950/20 border border-slate-100 dark:border-emerald-900/30 rounded-lg p-2 flex justify-between items-center">
                            <span className="text-[9px] uppercase tracking-widest text-slate-400 dark:text-emerald-500/60 font-bold">
                                Cleared Exams
                            </span>
                            <span className="text-sm font-mono text-slate-700 dark:text-emerald-300 font-bold">
                                {data.exams}
                            </span>
                        </div>
                        <button
                            onClick={() => {
                                fetch(`${API_BASE_URL}/api/academic/logout`, {
                                    method: "POST",
                                    headers: getAuthHeaders(),
                                }).then(() => setData(DEFAULT_DATA));
                            }}
                            className="mt-1 text-[9px] font-mono text-slate-400 hover:text-red-500 transition-colors uppercase text-center"
                        >
                            Terminate Connection
                        </button>
                    </div>
                )}
            </div>
        </BentoWidget>
    );
}
