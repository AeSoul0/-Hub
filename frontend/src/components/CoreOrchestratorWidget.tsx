"use client";

import { useState, useRef } from "react";
import { Terminal, Activity, Mic, Square, Loader2 } from "lucide-react";
import BentoWidget from "./BentoWidget";

export default function CoreOrchestratorWidget() {
    // Operational handling states mapping current telemetry actions inside runtime environments
    const [isListening, setIsListening] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [consoleOutput, setConsoleOutput] = useState("");

    // Instance bindings referencing raw user devices managed through HTML5 constraints
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<BlobPart[]>([]);

    // Initiates microphone telemetry streaming pipelines while managing structural access tokens
    const startRecording = async () => {
        try {
            setConsoleOutput("Initializing input matrix...");
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            audioChunksRef.current = [];

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunksRef.current.push(event.data);
                }
            };

            mediaRecorder.onstop = async () => {
                stream.getTracks().forEach(track => track.stop());
                const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
                await sendAudioToBackend(audioBlob);
            };

            mediaRecorder.start();
            setIsListening(true);
            setConsoleOutput("Stream active. Awaiting voice signal patterns...");
        } catch (error) {
            console.error("Microphone access error:", error);
            setConsoleOutput("FAULT: Authorization refused by external user settings.");
        }
    };

    // Closes recording stream processing triggers while safely shifting runtime state variables
    const stopRecording = () => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
            mediaRecorderRef.current.stop();
            setIsListening(false);
        }
    };

    // Forwards spatial audio fragments compiled locally over structural transmission bridges
    const sendAudioToBackend = async (blob: Blob) => {
        setIsProcessing(true);
        setConsoleOutput("Compressing dataset payloads for Whisper AI processing nodes...");

        try {
            const formData = new FormData();
            formData.append("file", blob, "voice_command.webm");

            /* Placeholder implementation boundary designed for upcoming cross-origin orchestration node calls
               ========================================================================
               const res = await fetch("http://127.0.0.1:3002/api/orchestrator/listen", {
                 method: "POST",
                 body: formData,
               });
               const data = await res.json();
               setConsoleOutput(data.transcription);
               ========================================================================
            */

            setTimeout(() => {
                setConsoleOutput("> Directives intercept confirmed: \"Toggle systemic light parameters and pool weather forecast inside Rome structure\".");
                setIsProcessing(false);
            }, 2000);

        } catch (err) {
            console.error("Transmission bridge fault:", err);
            setConsoleOutput("CRITICAL: Gateway sync failed. Host server unreachable.");
            setIsProcessing(false);
        }
    };

    // Maps external micro-interactions to state transition execution gates
    const handleMicToggle = () => {
        if (isProcessing) return;
        if (isListening) {
            stopRecording();
        } else {
            startRecording();
        }
    };

    return (
        <BentoWidget title="Core_Orchestrator" icon={Terminal} colorKey="cyan" colSpan={2}>
            <div className="flex flex-col justify-end h-full gap-4 mt-2">

                {/* Connectivity status telemetry component displaying active processing transitions */}
                <div className="flex items-center justify-between bg-white/50 dark:bg-white/[0.02] border border-cyan-500/30 dark:border-white/10 rounded-2xl p-3.5 backdrop-blur-lg transition-colors duration-300 hover:duration-75 ease-out">
                    <div className="flex items-center gap-4">
                        <div className={`relative flex items-center justify-center w-8 h-8 rounded-full border transition-colors duration-300 
              ${isProcessing ? 'bg-amber-500/10 border-amber-500/50 shadow-[0_0_15px_rgba(245,158,11,0.2)]' :
                                isListening ? 'bg-red-500/10 border-red-500/50 shadow-[0_0_15px_rgba(239,68,68,0.2)]' :
                                    'bg-cyan-500/10 border-cyan-500/20 shadow-[0_0_15px_rgba(6,182,212,0.1)]'}`}>

                            <div className={`absolute inset-0 rounded-full animate-ping opacity-50 
                ${isListening ? 'bg-red-500/20' : isProcessing ? 'bg-amber-500/20' : 'bg-cyan-500/20'}`} />

                            {isProcessing ? (
                                <Loader2 className="w-4 h-4 text-amber-500 animate-spin" />
                            ) : (
                                <Activity className={`w-4 h-4 animate-pulse ${isListening ? 'text-red-500' : 'text-cyan-600 dark:text-cyan-400'}`} />
                            )}
                        </div>

                        {/* Dynamic context frequency wave display synchronized across computational configurations */}
                        <div className={`flex items-end gap-1 h-5 transition-opacity duration-300 ${isProcessing ? 'opacity-30' : 'opacity-100'}`}>
                            <div className={`w-[3px] rounded-full animate-[wave-pulse_1s_ease-in-out_infinite] ${isListening ? 'bg-red-400' : 'bg-cyan-600/40 dark:bg-cyan-500/50'}`} style={{ animationDelay: '0.1s' }} />
                            <div className={`w-[3px] rounded-full animate-[wave-pulse_1.2s_ease-in-out_infinite] ${isListening ? 'bg-red-500' : 'bg-cyan-600/80 dark:bg-cyan-400'}`} style={{ animationDelay: '0.4s' }} />
                            <div className={`w-[3px] rounded-full animate-[wave-pulse_0.9s_ease-in-out_infinite] ${isListening ? 'bg-red-600' : 'bg-cyan-500 dark:bg-cyan-300'}`} style={{ animationDelay: '0.2s' }} />
                            <div className={`w-[3px] rounded-full animate-[wave-pulse_1.1s_ease-in-out_infinite] ${isListening ? 'bg-red-500' : 'bg-cyan-600/60 dark:bg-cyan-500/70'}`} style={{ animationDelay: '0.6s' }} />
                            <div className={`w-[3px] rounded-full animate-[wave-pulse_1.3s_ease-in-out_infinite] ${isListening ? 'bg-red-400' : 'bg-cyan-400 dark:bg-cyan-200'}`} style={{ animationDelay: '0.3s' }} />
                        </div>
                    </div>
                    <span className={`text-[10px] font-bold tracking-[0.2em] transition-colors duration-300 animate-[agent-linked-pulse_2s_ease-in-out_infinite]
            ${isProcessing ? 'text-amber-500' : isListening ? 'text-red-500' : 'text-cyan-700 dark:text-cyan-400'}`}>
                        {isProcessing ? "ANALYZING..." : isListening ? "RECORDING..." : "LINK_ACTIVE"}
                    </span>
                </div>

                {/* Input Text Console Layer */}
                <div className="relative flex items-center group/input">
                    <span className="absolute left-4 font-bold text-sm text-cyan-600/50 dark:text-cyan-400/50 group-hover/input:text-cyan-600 dark:group-hover/input:text-cyan-400 transition-colors duration-300 ease-out">&gt;</span>
                    <input
                        type="text"
                        readOnly
                        value={consoleOutput}
                        placeholder="Awaiting vocal directive..."
                        className="w-full bg-white dark:bg-[#0A101A]/40 border border-cyan-500/30 dark:border-white/10 rounded-xl py-3 pl-9 pr-14 text-xs font-bold text-slate-800 dark:text-cyan-50 placeholder-slate-400/80 dark:placeholder-cyan-700 focus:outline-none cursor-default shadow-[inset_0_2px_10px_rgba(0,0,0,0.02)] transition-colors duration-300 ease-out"
                    />

                    {/* Action Trigger Interface mapping system parameters to input behaviors */}
                    <button
                        onClick={handleMicToggle}
                        disabled={isProcessing}
                        className={`absolute right-1.5 p-2 rounded-lg cursor-pointer border transition-all duration-300 ease-out 
              ${isProcessing ? 'opacity-50 cursor-not-allowed bg-slate-100 dark:bg-cyan-500/5 text-slate-400 dark:text-cyan-500/40 border-transparent' :
                                isListening
                                    ? 'bg-red-500 dark:bg-red-500/20 text-white dark:text-red-400 border-red-600 dark:border-red-500/50 hover:bg-red-600 hover:scale-95'
                                    : 'bg-slate-100 dark:bg-cyan-500/10 text-slate-500 dark:text-cyan-500/60 hover:bg-slate-200 dark:hover:bg-cyan-500/20 hover:text-cyan-600 dark:hover:text-cyan-400 border-slate-200/80 dark:border-transparent'
                            }`}
                    >
                        {isListening ? <Square className="w-4 h-4 fill-current" /> : <Mic className="w-4 h-4" />}
                    </button>
                </div>
            </div>
        </BentoWidget>
    );
}