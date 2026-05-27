"use client";

import { useEffect, useState } from "react";
import { Activity, Sun, Moon } from "lucide-react";

interface HeaderProps {
    isDarkMode: boolean;
    toggleTheme: () => void;
}

export default function Header({ isDarkMode, toggleTheme }: HeaderProps) {
    const [backendStatus, setBackendStatus] = useState("Connecting...");

    useEffect(() => {
        fetch("http://127.0.0.1:3002/")
            .then((res) => res.json())
            .then((data) => setBackendStatus(data.status))
            .catch(() => setBackendStatus("Offline"));
    }, []);

    return (
        <header className="max-w-6xl mx-auto mb-12 flex justify-between items-center relative z-10">
            <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-white dark:bg-cyan-950/20 border border-slate-200/80 dark:border-cyan-500/20 backdrop-blur-md rounded-2xl flex items-center justify-center font-[family-name:var(--font-quicksand)] text-3xl font-bold text-cyan-700 dark:text-cyan-400 shadow-sm transition-transform duration-700 hover:scale-110">
                    Æ
                </div>
                <h1 className="text-3xl font-semibold tracking-wide text-slate-800 dark:text-cyan-50 font-[family-name:var(--font-quicksand)]">
                    Æ<span className="font-bold text-cyan-600 dark:text-cyan-400">Hub</span>
                </h1>
            </div>

            <div className="flex items-center gap-5">
                <div className="flex items-center gap-2 text-[10px] font-bold tracking-[0.2em] uppercase bg-white/70 dark:bg-cyan-950/20 backdrop-blur-md px-4 py-2 rounded-full border border-slate-200/80 dark:border-cyan-500/10 shadow-sm transition-colors duration-300">
                    <Activity className={`w-3.5 h-3.5 ${backendStatus === "Online" ? "text-cyan-600 dark:text-cyan-400 animate-pulse" : "text-red-600 dark:text-red-500"}`} />
                    <span className={backendStatus === "Online" ? "text-slate-600 dark:text-cyan-300/80" : "text-red-600 dark:text-red-500"}>
                        SYS_ {backendStatus}
                    </span>
                </div>

                <button
                    onClick={toggleTheme}
                    className="theme-transition-keep w-10 h-10 flex items-center justify-center overflow-hidden bg-white/70 dark:bg-cyan-950/20 backdrop-blur-md border border-slate-200/80 dark:border-cyan-500/10 rounded-full hover:scale-110 transition-transform duration-500 ease-out cursor-pointer relative shadow-sm"
                >
                    <Sun className={`theme-transition-keep absolute w-4 h-4 text-slate-600 transition-all duration-300 ease-out ${isDarkMode ? 'opacity-0 translate-y-6 scale-75' : 'opacity-100 translate-y-0 scale-100'}`} />
                    <Moon className={`theme-transition-keep absolute w-4 h-4 text-cyan-400 transition-all duration-300 ease-out ${isDarkMode ? 'opacity-100 translate-y-0 scale-100' : 'opacity-0 -translate-y-6 scale-75'}`} />
                </button>
            </div>
        </header>
    );
}