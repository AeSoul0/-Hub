"use client";

import { useEffect, useState } from "react";
import { GraduationCap, CheckCircle2, LogOut, Lock } from "lucide-react";
import BentoWidget from "./BentoWidget";

export default function AcademicWidget() {
    const [academicLogged, setAcademicLogged] = useState(false);
    const [academicLoading, setAcademicLoading] = useState(false);
    const [academicData, setAcademicData] = useState({ gpa: 0, exams: 0, cfu: 0 });

    useEffect(() => {
        async function checkAcademicStatus() {
            try {
                const res = await fetch("http://127.0.0.1:3002/api/academic/status");
                if (res.ok) {
                    const result = await res.json();
                    if (result.status === "success") {
                        setAcademicData(result.data);
                        setAcademicLogged(true);
                    }
                }
            } catch (e) {
                console.log("Academic cache check failed bounds");
            }
        }
        checkAcademicStatus();
    }, []);

    const handleSpidSync = async (e: React.MouseEvent) => {
        e.preventDefault();
        setAcademicLoading(true);
        try {
            const res = await fetch("http://127.0.0.1:3002/api/academic/login", { method: "POST" });
            if (res.ok) {
                const result = await res.json();
                setAcademicData(result.data);
                setAcademicLogged(true);
            } else {
                alert("SPID Authentication Timeout or Failed.");
            }
        } catch (err) {
            alert("Backend Core Engine Offline.");
        } finally {
            setAcademicLoading(false);
        }
    };

    const handleAcademicDisconnect = async (e: React.MouseEvent) => {
        e.preventDefault();
        try {
            const res = await fetch("http://127.0.0.1:3002/api/academic/logout", { method: "POST" });
            if (res.ok) {
                setAcademicLogged(false);
                setAcademicData({ gpa: 0, exams: 0, cfu: 0 });
            }
        } catch (err) {
            console.error("Purge session request failed network thresholds:", err);
        }
    };

    return (
        <BentoWidget
            title="Academic"
            icon={GraduationCap}
            colorKey="indigo"
            isLoading={academicLoading}
        >
            {academicLogged ? (
                <div className="flex flex-col h-full mt-2">
                    <div className="text-5xl font-[family-name:var(--font-quicksand)] font-semibold text-slate-900 dark:text-white">{academicData.gpa}</div>
                    <div className="text-[11px] font-bold uppercase tracking-wider text-indigo-600/60 mt-1">Average GPA</div>

                    <div className="mt-auto pt-4 border-t border-slate-200/70 dark:border-white/10 flex items-center justify-between gap-2 text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-indigo-400/60">
                        <div className="flex gap-4">
                            <div className="flex flex-col">
                                <span className="text-[9px] text-slate-400 dark:text-indigo-400/40">Exams</span>
                                <span className="text-slate-900 dark:text-white">16/23</span>
                            </div>
                            <div className="flex flex-col">
                                <span className="text-[9px] text-slate-400 dark:text-indigo-400/40">CFU</span>
                                <span className="text-slate-900 dark:text-white">129/180</span>
                            </div>
                        </div>
                        <button
                            onClick={handleAcademicDisconnect}
                            className="group/logout px-3 py-1.5 h-7 text-[10px] font-bold tracking-wider rounded-lg border border-indigo-500/30 dark:border-white/10 bg-slate-50 dark:bg-white/5 text-indigo-600 dark:text-indigo-400 hover:text-red-500 hover:bg-red-50 dark:hover:text-rose-400 dark:hover:bg-rose-500/10 hover:border-red-500/30 dark:hover:border-rose-500/20 uppercase transition-colors duration-75 ease-out flex items-center justify-center gap-1.5 cursor-pointer whitespace-nowrap"
                        >
                            <CheckCircle2 className="w-3 h-3 block group-hover/logout:hidden transition-none" />
                            <LogOut className="w-3 h-3 hidden group-hover/logout:block transition-none" />
                            <span className="block group-hover/logout:hidden tracking-widest transition-colors duration-75">Synced</span>
                            <span className="hidden group-hover/logout:block tracking-widest transition-colors duration-75">Reset</span>
                        </button>
                    </div>
                </div>
            ) : (
                <div className="flex flex-col h-full justify-between">
                    <p className="text-[10px] uppercase font-bold tracking-widest text-slate-400 dark:text-indigo-400/60 mt-2 text-center leading-relaxed">
                        Action Required:<br />Manual SPID Authentication
                    </p>
                    <button
                        onClick={handleSpidSync}
                        className="mt-auto w-full bg-slate-100 hover:bg-indigo-50 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-indigo-700 dark:text-indigo-400 text-[10px] font-bold uppercase tracking-[0.2em] py-3 rounded-lg transition-colors border border-indigo-500/20 flex items-center justify-center gap-2"
                    >
                        <Lock className="w-3.5 h-3.5" />
                        INITIATE SYNC
                    </button>
                </div>
            )}
        </BentoWidget>
    );
}