/**
 * @file frontend/src/components/layout/Header.tsx
 * @description Implements Header.tsx.
 * 
 * This module manages the frontend logic for Header.
 * Core interfaces: data structures.
 */
"use client";

import { useEffect, useState } from "react";
import { Activity } from "lucide-react";

import { fetchApi } from "@/lib/api/client";

export default function Header() {
    // Initialize backend connection status state
    // Initialize backend connection status state
    const [backendStatus, setBackendStatus] = useState("Connecting...");

    // Fetches the backend connection status on component mount
    useEffect(() => {
        fetchApi("/")
            .then((res) => res.json())
            .then((data) => setBackendStatus(data.status))
            .catch(() => setBackendStatus("Offline"));
    }, []);

    return (
        <header className="max-w-6xl mx-auto mb-12 flex justify-between items-center relative z-10">
            <div className="flex items-center gap-4">
                <h1 className="text-3xl font-semibold tracking-wide text-cyan-50 font-[family-name:var(--font-quicksand)]">
                    Æ<span className="font-bold text-cyan-400">Hub</span>
                </h1>
            </div>

            <div className="flex items-center gap-5">
                <div className="flex items-center gap-2 text-[10px] font-bold tracking-[0.2em] uppercase bg-cyan-950/20 backdrop-blur-md px-4 py-2 rounded-full border border-cyan-500/10 shadow-sm transition-colors duration-300">
                    <Activity
                        className={`w-3.5 h-3.5 ${backendStatus === "Online" ? "text-cyan-400 animate-pulse" : "text-cyan-500"}`}
                    />
                    <span
                        className={
                            backendStatus === "Online" ? "text-cyan-300/80" : "text-cyan-500"
                        }
                    >
                        SYS : Online {backendStatus}
                    </span>
                </div>
            </div>
        </header>
    );
}

