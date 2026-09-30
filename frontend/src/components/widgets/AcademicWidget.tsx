/**
 * @file frontend/src/components/widgets/AcademicWidget.tsx
 * @description Academic synchronization and progress widget.
 *
 * Provides the frontend controls for:
 * - loading academic statistics;
 * - triggering background synchronization;
 * - starting an interactive academic session;
 * - terminating the current academic connection.
 *
 * Authentication/session hardening remains centralized for the API layer and
 * should be migrated away from client-managed session identifiers in P2.
 */

"use client";

import { useEffect, useState } from "react";
import BentoWidget from "@/components/widgets/BentoWidget";
import { GraduationCap, LogIn, RefreshCcw } from "lucide-react";
import {
    PieChart,
    Pie,
    Cell,
    ResponsiveContainer,
    Tooltip,
} from "recharts";
import { fetchApi } from "@/lib/api/client";

// ============================================================================
// AUTHENTICATION HEADER COMPATIBILITY LAYER
// ============================================================================

/**
 * Builds the current compatibility authentication headers.
 *
 * NOTE:
 * This preserves the existing backend contract temporarily. The P2 identity
 * hardening phase will remove the client-managed X-Session-ID credential.
 */
const getAuthHeaders = (): Record<string, string> => {
    let sessionId = "default-session";

    if (typeof window !== "undefined") {
        sessionId =
            localStorage.getItem("aehub_session_id") ||
            "default-session";
    }

    return {
        "X-Session-ID": sessionId,
    };
};

// ============================================================================
// DOMAIN TYPES
// ============================================================================

type AcademicData = {
    gpa: number;
    exams: number;
    cfu: number;
};

const DEFAULT_DATA: AcademicData = {
    gpa: 0,
    exams: 0,
    cfu: 0,
};

// ============================================================================
// COMPONENT
// ============================================================================

export default function AcademicWidget() {
    const [data, setData] = useState<AcademicData>(DEFAULT_DATA);
    const [loading, setLoading] = useState<boolean>(true);
    const [isSyncing, setIsSyncing] = useState<boolean>(false);

    /**
     * Loads the latest academic data from the backend.
     */
    const loadAcademic = async () => {
        try {
            setLoading(true);

            const response = await fetchApi("/api/academic/status", {
                method: "GET",
                headers: getAuthHeaders(),
                credentials: "include",
            });

            if (!response.ok) {
                throw new Error(
                    `Academic status request failed: ${response.status}`,
                );
            }

            const json = await response.json();
            const payload = json?.data;

            if (payload) {
                setData({
                    gpa:
                        typeof payload.gpa === "number"
                            ? payload.gpa
                            : 0,
                    exams:
                        typeof payload.exams === "number"
                            ? payload.exams
                            : 0,
                    cfu:
                        typeof payload.cfu === "number"
                            ? payload.cfu
                            : 0,
                });
            } else {
                setData(DEFAULT_DATA);
            }
        } catch (error: unknown) {
            console.error("Academic data loading failed:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        void loadAcademic();
    }, []);

    /**
     * Requests a background academic synchronization.
     */
    const handleSync = async (event: React.FormEvent) => {
        event.preventDefault();
        setIsSyncing(true);

        try {
            const response = await fetchApi("/api/academic/sync", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...getAuthHeaders(),
                },
                credentials: "include",
            });

            if (response.ok) {
                window.setTimeout(() => {
                    void loadAcademic();
                    setIsSyncing(false);
                }, 10_000);
            } else {
                setIsSyncing(false);
            }
        } catch (error: unknown) {
            console.error("Academic synchronization failed:", error);
            setIsSyncing(false);
        }
    };

    /**
     * Requests an interactive academic login flow.
     */
    const handleInteractiveLogin = async (event: React.FormEvent) => {
        event.preventDefault();
        setIsSyncing(true);

        try {
            const response = await fetchApi(
                "/api/academic/interactive-login",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        ...getAuthHeaders(),
                    },
                    credentials: "include",
                },
            );

            if (response.ok) {
                window.setTimeout(() => {
                    void loadAcademic();
                    setIsSyncing(false);
                }, 20_000);
            } else {
                setIsSyncing(false);
            }
        } catch (error: unknown) {
            console.error("Interactive academic login failed:", error);
            setIsSyncing(false);
        }
    };

    /**
     * Terminates the current academic connection.
     */
    const handleLogout = async () => {
        try {
            await fetchApi("/api/academic/logout", {
                method: "POST",
                headers: getAuthHeaders(),
                credentials: "include",
            });
        } finally {
            setData(DEFAULT_DATA);
        }
    };

    const isAuthenticated = data.gpa > 0 || data.cfu > 0;

    return (
        <BentoWidget
            title="Academic_Sync"
            icon={GraduationCap}
            colorKey="emerald"
        >
            <div className="flex flex-col h-full mt-2 justify-between">
                {loading ? (
                    <div className="flex-1 flex items-center justify-center">
                        <RefreshCcw className="w-5 h-5 text-emerald-500/50 animate-spin" />
                    </div>
                ) : !isAuthenticated ? (
                    <div className="flex flex-col gap-2 h-full justify-center">
                        <span className="text-[10px] font-mono text-emerald-600/70 dark:text-emerald-400/70 uppercase tracking-wider text-center mb-2">
                            Session Missing or Expired
                        </span>

                        <button
                            type="button"
                            onClick={(event) => void handleSync(event)}
                            disabled={isSyncing}
                            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 font-bold text-[10px] uppercase tracking-widest transition-colors disabled:opacity-50"
                        >
                            {isSyncing ? (
                                <>
                                    <RefreshCcw className="w-3 h-3 animate-spin" />
                                    Syncing Node...
                                </>
                            ) : (
                                <>
                                    <RefreshCcw className="w-3 h-3" />
                                    Background Sync
                                </>
                            )}
                        </button>

                        <button
                            type="button"
                            onClick={(event) => void handleInteractiveLogin(event)}
                            disabled={isSyncing}
                            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-emerald-700/20 hover:bg-emerald-700/40 text-emerald-600 dark:text-emerald-300 font-bold text-[10px] uppercase tracking-widest transition-colors disabled:opacity-50"
                        >
                            {isSyncing ? (
                                <>
                                    <RefreshCcw className="w-3 h-3 animate-spin" />
                                    Waiting for Login...
                                </>
                            ) : (
                                <>
                                    <LogIn className="w-3 h-3" />
                                    Rinnova Sessione (Interactive)
                                </>
                            )}
                        </button>
                    </div>
                ) : (
                    <div className="flex flex-col h-full justify-between">
                        <div className="flex-1 flex items-center justify-center gap-4">
                            <div className="h-28 w-28 shrink-0 relative">
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={[
                                                {
                                                    name: "Acquisiti",
                                                    value: data.cfu,
                                                },
                                                {
                                                    name: "Mancanti",
                                                    value: Math.max(
                                                        0,
                                                        180 - data.cfu,
                                                    ),
                                                },
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
                                            contentStyle={{
                                                backgroundColor: "#020617",
                                                border: "1px solid rgba(16, 185, 129, 0.2)",
                                                fontSize: "10px",
                                                borderRadius: "8px",
                                            }}
                                            itemStyle={{ color: "#34d399" }}
                                        />
                                    </PieChart>
                                </ResponsiveContainer>

                                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none mt-1">
                                    <span className="text-[12px] font-mono font-bold text-emerald-400 leading-none">
                                        {data.cfu}
                                    </span>
                                    <span className="text-[8px] text-emerald-600/70 uppercase font-bold tracking-widest mt-1">
                                        CFU
                                    </span>
                                </div>
                            </div>

                            <div className="flex flex-col gap-2 flex-1">
                                <div className="bg-slate-50 dark:bg-emerald-950/20 border border-slate-100 dark:border-emerald-900/30 rounded-lg p-2.5 flex flex-col justify-center">
                                    <span className="text-[9px] uppercase tracking-widest text-slate-400 dark:text-emerald-500/60 font-bold mb-1">
                                        Media (GPA)
                                    </span>
                                    <span className="text-lg leading-none font-mono text-slate-700 dark:text-emerald-300 font-bold">
                                        {data.gpa.toFixed(2)}
                                    </span>
                                </div>

                                <div className="bg-slate-50 dark:bg-emerald-950/20 border border-slate-100 dark:border-emerald-900/30 rounded-lg p-2.5 flex flex-col justify-center">
                                    <span className="text-[9px] uppercase tracking-widest text-slate-400 dark:text-emerald-500/60 font-bold mb-1">
                                        Esami
                                    </span>
                                    <span className="text-lg leading-none font-mono text-slate-700 dark:text-emerald-300 font-bold">
                                        {data.exams}
                                    </span>
                                </div>
                            </div>
                        </div>

                        <button
                            type="button"
                            onClick={() => void handleLogout()}
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