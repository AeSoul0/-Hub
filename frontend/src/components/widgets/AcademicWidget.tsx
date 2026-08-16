"use client";

import { useEffect, useState } from "react";
import BentoWidget from "@/components/widgets/BentoWidget";
import { GraduationCap, LogIn, RefreshCcw } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

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
        setIsSyncing(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/academic/sync`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...getAuthHeaders(),
                },
            });

            if (res.ok) {
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

    const handleInteractiveLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsSyncing(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/academic/interactive-login`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...getAuthHeaders(),
                },
            });

            if (res.ok) {
                // Wait longer for interactive login to complete
                setTimeout(() => {
                    loadAcademic();
                    setIsSyncing(false);
                }, 20000);
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
                    // UNAUTHENTICATED STATE: Prompt for Sync or Auth
                    <div className="flex flex-col gap-2 h-full justify-center">
                        <span className="text-[10px] font-mono text-emerald-600/70 dark:text-emerald-400/70 uppercase tracking-wider text-center mb-2">
                            Session Missing or Expired
                        </span>
                        
                        <button
                            onClick={handleSync}
                            disabled={isSyncing}
                            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 font-bold text-[10px] uppercase tracking-widest transition-colors disabled:opacity-50"
                        >
                            {isSyncing ? (
                                <>
                                    <RefreshCcw className="w-3 h-3 animate-spin" /> Syncing Node...
                                </>
                            ) : (
                                <>
                                    <RefreshCcw className="w-3 h-3" /> Background Sync
                                </>
                            )}
                        </button>

                        <button
                            onClick={handleInteractiveLogin}
                            disabled={isSyncing}
                            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-emerald-700/20 hover:bg-emerald-700/40 text-emerald-600 dark:text-emerald-300 font-bold text-[10px] uppercase tracking-widest transition-colors disabled:opacity-50"
                        >
                            {isSyncing ? (
                                <>
                                    <RefreshCcw className="w-3 h-3 animate-spin" /> Waiting for Login...
                                </>
                            ) : (
                                <>
                                    <LogIn className="w-3 h-3" /> Rinnova Sessione (Interactive)
                                </>
                            )}
                        </button>
                    </div>
                ) : (
                    // AUTHENTICATED STATE: Render Extracted Metrics
                    <div className="flex flex-col h-full justify-between">
                        <div className="flex-1 flex items-center justify-center gap-4">
                            {/* Recharts PieChart for CFU progress (assuming 180 as target) */}
                            <div className="h-28 w-28 shrink-0 relative">
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={[
                                                { name: "Acquisiti", value: data.cfu },
                                                { name: "Mancanti", value: Math.max(0, 180 - data.cfu) }
                                            ]}
                                            dataKey="value"
                                            innerRadius={30}
                                            outerRadius={45}
                                            stroke="none"
                                            startAngle={90}
                                            endAngle={-270}
                                        >
                                            <Cell fill="#10b981" />
                                            <Cell fill="rgba(16, 185, 129, 0.1)" />
                                        </Pie>
                                        <Tooltip 
                                            contentStyle={{ backgroundColor: '#020617', border: '1px solid rgba(16, 185, 129, 0.2)', fontSize: '10px', borderRadius: '8px' }} 
                                            itemStyle={{ color: '#34d399' }} 
                                        />
                                    </PieChart>
                                </ResponsiveContainer>
                                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none mt-1">
                                    <span className="text-[12px] font-mono font-bold text-emerald-400 leading-none">{data.cfu}</span>
                                    <span className="text-[8px] text-emerald-600/70 uppercase font-bold tracking-widest mt-1">CFU</span>
                                </div>
                            </div>

                            {/* Stats */}
                            <div className="flex flex-col gap-2 flex-1">
                                <div className="bg-slate-50 dark:bg-emerald-950/20 border border-slate-100 dark:border-emerald-900/30 rounded-lg p-2.5 flex flex-col justify-center">
                                    <span className="text-[9px] uppercase tracking-widest text-slate-400 dark:text-emerald-500/60 font-bold mb-1">Media (GPA)</span>
                                    <span className="text-lg leading-none font-mono text-slate-700 dark:text-emerald-300 font-bold">{data.gpa.toFixed(2)}</span>
                                </div>
                                <div className="bg-slate-50 dark:bg-emerald-950/20 border border-slate-100 dark:border-emerald-900/30 rounded-lg p-2.5 flex flex-col justify-center">
                                    <span className="text-[9px] uppercase tracking-widest text-slate-400 dark:text-emerald-500/60 font-bold mb-1">Esami</span>
                                    <span className="text-lg leading-none font-mono text-slate-700 dark:text-emerald-300 font-bold">{data.exams}</span>
                                </div>
                            </div>
                        </div>

                        <button
                            onClick={() => {
                                fetch(`${API_BASE_URL}/api/academic/logout`, {
                                    method: "POST",
                                    headers: getAuthHeaders(),
                                }).then(() => setData(DEFAULT_DATA));
                            }}
                            className="mt-3 text-[9px] font-mono text-slate-400 hover:text-red-500 transition-colors uppercase text-center w-full py-1 border border-transparent hover:border-red-900/30 rounded-lg hover:bg-red-900/10"
                        >
                            Terminate Connection
                        </button>
                    </div>
                )}
            </div>
        </BentoWidget>
    );
}

