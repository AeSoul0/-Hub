"use client";

import { useState } from "react";
import { Play, Search, Download, Activity, CheckCircle2 } from "lucide-react";
import BentoWidget from "./BentoWidget";

export default function MediaSyncWidget() {
    const [mediaQuery, setMediaQuery] = useState("");
    const [mediaStatus, setMediaStatus] = useState<"idle" | "searching" | "downloading" | "done">("idle");

    const handleMediaDownload = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!mediaQuery) return;
        setMediaStatus("searching");

        try {
            const response = await fetch("http://127.0.0.1:3002/api/media/download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query: mediaQuery }),
            });

            if (response.ok) {
                setMediaStatus("downloading");
                const disposition = response.headers.get('Content-Disposition');
                let filename = `${mediaQuery}.mp3`;
                if (disposition && disposition.includes('filename=')) {
                    const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
                    const matches = filenameRegex.exec(disposition);
                    if (matches != null && matches[1]) {
                        filename = matches[1].replace(/['"]/g, '');
                    }
                }
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);

                setMediaStatus("done");
                setTimeout(() => { setMediaStatus("idle"); setMediaQuery(""); }, 4000);
            } else {
                setMediaStatus("idle");
            }
        } catch (err) {
            console.error(err);
            setMediaStatus("idle");
        }
    };

    return (
        <BentoWidget title="Mp3 - Extractor" icon={Play} colorKey="rose">
            <div className="flex flex-col h-full mt-2 justify-between">
                <form onSubmit={handleMediaDownload} className="relative flex items-center group/search mt-auto mb-3">
                    <Search className="absolute left-2.5 w-3.5 h-3.5 text-slate-400 dark:text-rose-500/50 group-hover/search:text-rose-600 dark:group-hover/search:text-rose-400 transition-colors duration-300 group-hover/search:duration-75" />
                    <input
                        value={mediaQuery}
                        onChange={(e) => setMediaQuery(e.target.value)}
                        disabled={mediaStatus !== "idle"}
                        type="text"
                        placeholder="Artist - Title..."
                        className="w-full bg-slate-50 dark:bg-slate-900/40 border border-rose-500/30 dark:border-rose-500/20 rounded-lg py-2 pl-8 pr-10 text-[11px] font-bold text-slate-800 dark:text-rose-50 placeholder-slate-400 dark:placeholder-rose-700/60 focus:outline-none focus:border-rose-500 transition-colors duration-300 focus:duration-75 disabled:opacity-50"
                    />
                    <button disabled={mediaStatus !== "idle" || !mediaQuery} type="submit" className="absolute right-1.5 p-1.5 rounded-md bg-slate-200 hover:bg-rose-100 dark:bg-rose-500/10 dark:hover:bg-rose-500/20 text-slate-500 hover:text-rose-600 dark:text-rose-400 disabled:opacity-50 transition-colors duration-300 hover:duration-75 cursor-pointer">
                        <Download className="w-3.5 h-3.5" />
                    </button>
                </form>
                <div className="pt-3 border-t border-slate-200/80 dark:border-rose-500/10 flex items-center justify-center">
                    {mediaStatus === "idle" && <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-rose-400/40">Ready to Extract</span>}
                    {mediaStatus === "searching" && <span className="text-[10px] font-bold uppercase tracking-widest text-rose-600 dark:text-rose-400 animate-pulse flex items-center gap-2"><Activity className="w-3 h-3" /> Converting 320kbps...</span>}
                    {mediaStatus === "downloading" && (
                        <div className="w-full flex flex-col gap-1.5">
                            <div className="w-full bg-slate-200 dark:bg-rose-950/30 rounded-full h-1 overflow-hidden">
                                <div className="bg-rose-500 h-full w-2/3 animate-[pulse_1s_ease-in-out_infinite]" />
                            </div>
                            <span className="text-[9px] font-mono text-center text-rose-600 dark:text-rose-400">Extracting Audio...</span>
                        </div>
                    )}
                    {mediaStatus === "done" && <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-600 dark:text-emerald-400 flex items-center gap-2"><CheckCircle2 className="w-3 h-3" /> Saved to Server</span>}
                </div>
            </div>
        </BentoWidget>
    );
}