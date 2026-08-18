/**
 * @file frontend/src/app/page.tsx
 * @description Core module for A.U.R.O.R.A. System
 *
 * Implements primary logic and architectural constraints.
 *
 * Architectural constraints and responsibilities apply here.
 * Testability and dependency separation are enforced.
 */

"use client";

import { useEffect, useState } from "react";
import Header from "../components/layout/Header";
import CoreOrchestratorWidget from "../components/widgets/CoreOrchestratorWidget";
import TerminalLog from "../components/layout/TerminalLog";
import WorkspaceDesktop from "../components/layout/WorkspaceDesktop";

export default function Home() {
    const [isDarkMode, setIsDarkMode] = useState(true);

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setIsDarkMode(document.documentElement.classList.contains("dark"));
    }, []);

    const toggleTheme = () => {
        const updateDOM = () => {
            const isDark = document.documentElement.classList.contains("dark");

            if (isDark) {
                document.documentElement.classList.remove("dark");
                localStorage.setItem("theme", "light");
                setIsDarkMode(false);
            } else {
                document.documentElement.classList.add("dark");
                localStorage.setItem("theme", "dark");
                setIsDarkMode(true);
            }
        };

        if (document.startViewTransition) {
            document.startViewTransition(updateDOM);
        } else {
            updateDOM();
        }
    };

    return (
        <div className="min-h-screen flex text-slate-800 dark:text-cyan-50 font-[family-name:var(--font-geist-sans)] relative overflow-x-hidden">
            {/* Background layers */}
            <div className="fixed inset-0 holographic-space pointer-events-none -z-20" />
            <div className="fixed top-0 left-0 w-full h-[200vh] depth-mesh pointer-events-none -z-20 opacity-50" />

            <div className="flex-1 flex flex-col h-screen overflow-hidden relative">
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                <Header {...({ isDarkMode, toggleTheme } as any)} />
                <WorkspaceDesktop />

                <div className="flex-1 flex flex-col overflow-hidden p-4 sm:p-6 gap-4 sm:gap-6">
                    {/* MAIN WORKSPACE - Minimal, Cinematic & Centered */}
                    <main
                        className="
                          flex-1
                          overflow-y-auto custom-scrollbar
                          flex flex-col xl:flex-row
                          items-center justify-center
                          gap-8 xl:gap-16
                          relative z-10
                          p-4 sm:p-10
                        "
                    >
                        {/* CENTER: AI WIDGET (Spotlight) */}
                        <div className="w-full max-w-3xl h-[350px] xl:h-[450px] shrink-0 relative group">
                            {/* Ambient glow behind the AI core */}
                            <div className="absolute inset-0 bg-cyan-500/5 rounded-[2.5rem] blur-3xl group-hover:bg-cyan-500/10 transition-colors duration-500 -z-10" />
                            <CoreOrchestratorWidget />
                        </div>

                        {/* RIGHT: TERMINAL (Discreet Activity Log) */}
                        <div className="w-full max-w-3xl xl:w-[400px] h-[300px] xl:h-[450px] shrink-0 opacity-70 hover:opacity-100 transition-opacity duration-500">
                            <TerminalLog />
                        </div>

                        {/* 
                          ========================================================================
                          DYNAMIC CONTEXTUAL WINDOWS AREA (AGENT-READY ARCHITECTURE)
                          ========================================================================
                          Future widgets (Music Player, Weather, Analysis, Maps) will be rendered 
                          here dynamically based on the AI's state and responses, rather than 
                          permanently occupying space. 
                          
                          "L'interfaccia si adatta all'intelligenza."
                        */}
                    </main>
                </div>
            </div>
        </div>
    );
}

