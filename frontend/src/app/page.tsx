"use client";

import { useEffect, useState } from "react";
import Header from "../components/Header";
import WeatherWidget from "../components/WeatherWidget";
import AcademicWidget from "../components/AcademicWidget";
import Yt_To_Mp3_Widget from "../components/Yt_To_Mp3_Widget";
import AudioPlayerWidget from "../components/AudioPlayerWidget";
import CoreOrchestratorWidget from "../components/CoreOrchestratorWidget";
import BentoWidget from "../components/BentoWidget";
import Sidebar from "../components/Sidebar";
import TerminalLog from "../components/TerminalLog";
import { LayoutDashboard } from "lucide-react";

export default function Home() {
    const [isDarkMode, setIsDarkMode] = useState(true);

    useEffect(() => {
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

            <Sidebar />

            <div className="flex-1 flex flex-col h-screen overflow-hidden">
                <Header {...({ isDarkMode, toggleTheme } as any)} />

                <div className="flex-1 flex flex-col lg:flex-row overflow-hidden p-4 sm:p-6 gap-4 sm:gap-6">
                    {/* MAIN WORKSPACE (Center) */}
                    <main
                        className="
                          flex-1
                          overflow-y-auto custom-scrollbar
                          grid gap-4 sm:gap-6
                          grid-cols-1
                          sm:grid-cols-2
                          auto-rows-[200px] sm:auto-rows-[240px]
                          items-stretch
                          relative z-10
                        "
                    >
                        {/* Core Orchestrator is the Spotlight */}
                        <div className="col-span-1 sm:col-span-2">
                            <CoreOrchestratorWidget />
                        </div>

                        <WeatherWidget />
                        <AcademicWidget />
                        <Yt_To_Mp3_Widget />
                        <AudioPlayerWidget />

                        <BentoWidget
                            variant="slot"
                            title={
                                <>
                                    Module
                                    <br />
                                    Alpha
                                </>
                            }
                            icon={LayoutDashboard}
                            colorKey="cyan"
                        />
                    </main>

                    {/* TERMINAL LOG (Right Panel) */}
                    <aside className="w-full lg:w-96 shrink-0 h-[400px] lg:h-full relative z-10">
                        <TerminalLog />
                    </aside>
                </div>
            </div>
        </div>
    );
}
