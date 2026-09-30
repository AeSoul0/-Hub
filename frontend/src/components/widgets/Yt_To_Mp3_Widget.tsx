/**
 * @file frontend/src/components/widgets/Yt_To_Mp3_Widget.tsx
 * @description Media extraction widget for backend-managed downloads.
 *
 * Provides:
 * - media query submission;
 * - download state tracking;
 * - Content-Disposition filename handling;
 * - browser-side download initiation.
 *
 * Network communication is centralized through the shared API client.
 */

"use client";

import { useState } from "react";
import {
    Activity,
    CheckCircle2,
    Download,
    Play,
    Search,
} from "lucide-react";
import BentoWidget from "@/components/widgets/BentoWidget";
import { fetchApi } from "@/lib/api/client";

// ==============================================================================
// COMPATIBILITY AUTHENTICATION LAYER
// ==============================================================================

/**
 * Returns the legacy session header used by the current backend contract.
 *
 * P2 will replace client-managed session identifiers with secure cookies.
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

// ==============================================================================
// COMPONENT
// ==============================================================================

export default function MediaSyncWidget() {
    const [mediaQuery, setMediaQuery] = useState("");
    const [mediaStatus, setMediaStatus] = useState<
        "idle" | "searching" | "downloading" | "done"
    >("idle");

    /**
     * Executes the media extraction request.
     */
    const handleMediaDownload = async (
        event: React.FormEvent,
    ) => {
        event.preventDefault();

        const query = mediaQuery.trim();

        if (!query || mediaStatus !== "idle") {
            return;
        }

        setMediaStatus("searching");

        try {
            const response = await fetchApi(
                "/api/media/download",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        ...getAuthHeaders(),
                    },
                    body: JSON.stringify({ query }),
                    credentials: "include",
                },
            );

            if (!response.ok) {
                throw new Error(
                    `Media download request failed: ${response.status}`,
                );
            }

            setMediaStatus("downloading");

            const disposition =
                response.headers.get("Content-Disposition");

            let filename = `${query}.mp3`;

            if (disposition) {
                const filenameMatch = disposition.match(
                    /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/i,
                );

                if (filenameMatch?.[1]) {
                    filename = filenameMatch[1]
                        .replace(/[\'"]/g, "")
                        .trim();
                }
            }

            const blob = await response.blob();
            const objectUrl = window.URL.createObjectURL(blob);

            try {
                const anchor = document.createElement("a");
                anchor.href = objectUrl;
                anchor.download = filename;
                document.body.appendChild(anchor);
                anchor.click();
                anchor.remove();
            } finally {
                window.URL.revokeObjectURL(objectUrl);
            }

            setMediaStatus("done");

            window.setTimeout(() => {
                setMediaStatus("idle");
                setMediaQuery("");
            }, 4_000);
        } catch (error: unknown) {
            console.error("Media extraction request failed:", error);
            setMediaStatus("idle");
        }
    };

    return (
        <BentoWidget
            title="Mp3 - Extractor"
            icon={Play}
            colorKey="rose"
        >
            <div className="flex flex-col h-full mt-2 justify-between">
                <form
                    onSubmit={(event) => void handleMediaDownload(event)}
                    className="relative flex items-center group/search mt-auto mb-3"
                >
                    <Search className="absolute left-2.5 w-3.5 h-3.5 text-slate-400 dark:text-rose-500/50" />

                    <input
                        value={mediaQuery}
                        onChange={(event) =>
                            setMediaQuery(event.target.value)
                        }
                        disabled={mediaStatus !== "idle"}
                        type="text"
                        placeholder="Artist - Title..."
                        className="w-full bg-slate-50 dark:bg-slate-900/40 border border-rose-500/30 dark:border-rose-500/20 rounded-lg py-2 pl-8 pr-10 text-[11px] font-bold text-slate-800 dark:text-rose-50 placeholder-slate-400 dark:placeholder-rose-700/60 focus:outline-none focus:border-rose-500 disabled:opacity-50"
                    />

                    <button
                        type="submit"
                        disabled={
                            mediaStatus !== "idle" ||
                            !mediaQuery.trim()
                        }
                        aria-label="Download media"
                        className="absolute right-1.5 p-1.5 rounded-md bg-slate-200 hover:bg-rose-100 dark:bg-rose-500/10 dark:hover:bg-rose-500/20 text-slate-500 hover:text-rose-600 dark:text-rose-400 disabled:opacity-50"
                    >
                        <Download className="w-3.5 h-3.5" />
                    </button>
                </form>

                <div className="pt-3 border-t border-slate-200/80 dark:border-rose-500/10 flex items-center justify-center">
                    {mediaStatus === "idle" && (
                        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-rose-400/40">
                            Ready to Extract
                        </span>
                    )}

                    {mediaStatus === "searching" && (
                        <span className="text-[10px] font-bold uppercase tracking-widest text-rose-600 dark:text-rose-400 animate-pulse flex items-center gap-2">
                            <Activity className="w-3 h-3" />
                            Converting...
                        </span>
                    )}

                    {mediaStatus === "downloading" && (
                        <div className="w-full flex flex-col gap-1.5">
                            <div className="w-full bg-slate-200 dark:bg-rose-950/30 rounded-full h-1 overflow-hidden">
                                <div className="bg-rose-500 h-full w-2/3 animate-pulse" />
                            </div>

                            <span className="text-[9px] font-mono text-center text-rose-600 dark:text-rose-400">
                                Extracting Audio...
                            </span>
                        </div>
                    )}

                    {mediaStatus === "done" && (
                        <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
                            <CheckCircle2 className="w-3 h-3" />
                            Saved Successfully
                        </span>
                    )}
                </div>
            </div>
        </BentoWidget>
    );
}
