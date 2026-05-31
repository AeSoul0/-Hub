"use client";

import { useState, useRef } from "react";
import { Terminal, Activity, Mic, Square, Loader2, Cpu, Wifi } from "lucide-react";
import BentoWidget from "./BentoWidget";
import { useAppStore } from "../store/index"; // Import the Global State memory

// ==============================================================================
// SYSTEM PROMPT & BEHAVIORAL DIRECTIVES
// ==============================================================================
const ATOM_SYSTEM_PROMPT = `You are Atom, the voice assistant of AeHub. 
CRITICAL DIRECTIVE: You are speaking aloud. You MUST be radically concise and sound like a normal, direct human.

1. EXTREME BREVITY: Answer in 1 short sentence whenever possible. Never exceed 2 short sentences. Go straight to the core answer immediately.
2. NO ROBOTIC JARGON: Never describe yourself as a "highly advanced artificial intelligence", "architecture", or "cognitive engine". If asked who you are, just say "I'm Atom, your AeHub assistant."
3. NO SYMBOLS/MARKDOWN: No asterisks, brackets, hashes, or code. Speak naturally.
4. NATURAL CONVERSATION: Do not use filler words, robotic transitions, or overly polite greetings. Just deliver the answer cleanly and quickly.`;

export default function CoreOrchestratorWidget() {
    // Operation handling states for tracking microphone telemetry, keyboard queries and backend states
    const [isListening, setIsListening] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [inputText, setInputText] = useState("");

    // ==============================================================================
    // GLOBAL STATE SUBSCRIPTIONS
    // Extracting live telemetry from the Zustand Global Store to provide system awareness
    // ==============================================================================
    const liveWeatherData = useAppStore((state) => state.weatherData);
    const liveMediaStatus = useAppStore((state) => state.mediaConverterStatus);
    const liveMusicData = useAppStore((state) => state.musicPlayerData);
    const liveAcademicData = useAppStore((state) => state.academicData);

    // Hook bindings targeting capture hardware resources through standard browser capabilities
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<BlobPart[]>([]);

    // ==============================================================================
    // DYNAMIC UI CONTEXT AGGREGATOR
    // ==============================================================================
    const getLiveSystemContext = () => {
        // Compiles the live system dashboard state into a JSON payload for context injection
        const dashboardState = {
            systemTime: new Date().toLocaleTimeString('it-IT'),
            weatherWidgetTelemetry: liveWeatherData,
            mediaConverterTelemetry: liveMediaStatus,
            musicPlayerTelemetry: liveMusicData,
            academicModuleTelemetry: liveAcademicData
        };
        return JSON.stringify(dashboardState, null, 2);
    };

    // ==============================================================================
    // VOCAL STREAM INPUT PIPELINE
    // ==============================================================================
    const startRecording = async () => {
        try {
            setInputText("Initializing input matrix...");

            // ===============================
            // SAFE MEDIA DEVICE CHECK
            // ===============================
            if (
                typeof navigator === "undefined" ||
                !navigator.mediaDevices ||
                !navigator.mediaDevices.getUserMedia
            ) {
                setInputText("MIC NOT SUPPORTED ON THIS DEVICE");
                return;
            }

            const stream = await navigator.mediaDevices.getUserMedia({
                audio: true,
            });

            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            audioChunksRef.current = [];

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunksRef.current.push(event.data);
                }
            };

            mediaRecorder.onstop = async () => {
                stream.getTracks().forEach((track) => track.stop());
                const audioBlob = new Blob(audioChunksRef.current, {
                    type: "audio/webm",
                });
                await sendVoiceToBackend(audioBlob);
            };

            mediaRecorder.start();
            setIsListening(true);
            setInputText("Stream active. Awaiting voice signal patterns...");
        } catch (error) {
            console.error("Microphone access error:", error);
            setInputText("MIC ACCESS DENIED OR UNSUPPORTED DEVICE");
        }
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
            mediaRecorderRef.current.stop();
            setIsListening(false);
        }
    };

    const sendVoiceToBackend = async (blob: Blob) => {
        setIsProcessing(true);
        setInputText("Compressing dataset payloads for orchestration nodes...");
        try {
            const formData = new FormData();
            formData.append("file", blob, "voice_command.webm");
            formData.append("system_prompt", ATOM_SYSTEM_PROMPT);
            // Injecting the live Dashboard UI Context into the API transmission packet
            formData.append("ui_context", getLiveSystemContext());

            const res = await fetch("http://192.168.1.216:3002/api/orchestrator/listen", {
                method: "POST",
                body: formData,
            });

            await handleBackendResponse(res);
        } catch (err) {
            setInputText("CRITICAL: Gateway sync failed. Host server unreachable.");
            setIsProcessing(false);
        }
    };

    // ==============================================================================
    // KEYBOARD DIRECTIVE INPUT PIPELINE
    // ==============================================================================
    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter" && inputText.trim() !== "") {
            sendTextToBackend(inputText);
        }
    };

    const sendTextToBackend = async (text: string) => {
        setIsProcessing(true);
        setInputText("TRANSMITTING TEXT DIRECTIVE...");
        try {
            const formData = new FormData();
            formData.append("text", text);
            formData.append("system_prompt", ATOM_SYSTEM_PROMPT);
            // Injecting the live Dashboard UI Context into the API transmission packet
            formData.append("ui_context", getLiveSystemContext());

            const res = await fetch("http://127.0.0.1:3002/api/orchestrator/ask", {
                method: "POST",
                body: formData,
            });

            await handleBackendResponse(res);
        } catch (err) {
            setInputText("CRITICAL: Gateway sync failed. Host server unreachable.");
            setIsProcessing(false);
        }
    };

    // ==============================================================================
    // ARCHITECTURAL RESPONSE RECOVERY LAYERS
    // ==============================================================================
    const handleBackendResponse = async (res: Response) => {
        if (!res.ok) throw new Error("Backend orchestration node returned an error response");
        const data = await res.json();

        // Wipe the input bar to maintain a clean, minimalist HUD interface layout
        setInputText("");

        // Initialize seamless audio transmission playback via native window media controllers
        if (data.audio_base64) {
            const audio = new Audio(`data:audio/mp3;base64,${data.audio_base64}`);
            await audio.play();
        }
        setIsProcessing(false);
    };

    const handleMicToggle = () => {
        if (isProcessing) return;
        if (isListening) stopRecording();
        else startRecording();
    };

    // ==============================================================================
    // HUD RENDERER
    // ==============================================================================
    return (
        <BentoWidget title="ATOM_CORE" icon={Terminal} colorKey="cyan" colSpan={2}>
            {/* HUD Framework Main Shell Layout */}
            <div className="relative flex flex-col justify-between h-full w-full mt-2 rounded-xl overflow-hidden bg-gradient-to-br from-[#020813] to-[#0a1122] border border-cyan-900/50 p-4 shadow-[inset_0_0_40px_rgba(6,182,212,0.03)]">

                {/* Decorative Hologram Grid Overlay Matrix */}
                <div className="absolute inset-0 bg-[linear-gradient(rgba(6,182,212,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(6,182,212,0.05)_1px,transparent_1px)] bg-[size:16px_16px] pointer-events-none opacity-50" />

                {/* Top Telemetry Feed Layout */}
                <div className="relative flex justify-between items-center w-full mb-4 font-mono text-[9px] text-cyan-500/60 uppercase tracking-widest z-10">
                    <div className="flex items-center gap-2">
                        <Cpu className="w-3 h-3 text-cyan-600" />
                        <span>SYS.CORE // ATOM_PROCESSOR_v.120B</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <span>UPLINK: SECURE_LINK</span>
                        <Wifi className="w-3 h-3 text-cyan-600" />
                    </div>
                </div>

                {/* Central Orchestrator Interface Array */}
                <div className="relative flex flex-col gap-4 z-10 w-full mt-auto">

                    {/* Centered Telemetry Status Field */}
                    <div className="flex items-center justify-center gap-6 bg-[#040d1a]/80 border border-cyan-500/20 rounded-lg p-3 backdrop-blur-md transition-all duration-300">
                        <div className="flex items-center gap-4">
                            {/* System Status Visual Beacon */}
                            <div className={`relative flex items-center justify-center w-8 h-8 rounded-md border transition-all duration-300 
                                ${isProcessing ? 'bg-amber-500/10 border-amber-500/50 shadow-[0_0_15px_rgba(245,158,11,0.2)]' :
                                    isListening ? 'bg-red-500/10 border-red-500/50 shadow-[0_0_15px_rgba(239,68,68,0.3)]' :
                                        'bg-cyan-500/10 border-cyan-500/30 shadow-[0_0_15px_rgba(6,182,212,0.1)]'}`}>

                                <div className={`absolute inset-0 rounded-md animate-ping opacity-40 
                                    ${isListening ? 'bg-red-500/30' : isProcessing ? 'bg-amber-500/30' : 'bg-cyan-500/20'}`} />

                                {isProcessing ? (
                                    <Loader2 className="w-4 h-4 text-amber-500 animate-spin" />
                                ) : (
                                    <Activity className={`w-4 h-4 animate-pulse ${isListening ? 'text-red-500' : 'text-cyan-400'}`} />
                                )}
                            </div>

                            {/* Soundwave Telemetry Simulation Fields */}
                            <div className="flex items-end gap-[2px] h-5 to-indigo-500">
                                {[0.1, 0.4, 0.2, 0.6, 0.3, 0.5].map((delay, i) => (
                                    <div key={i}
                                        className={`w-[3px] rounded-sm animate-[wave-pulse_1s_ease-in-out_infinite] 
                                         ${isListening ? 'bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.5)]' : 'bg-cyan-500/70 shadow-[0_0_5px_rgba(6,182,212,0.3)]'}`}
                                        style={{ animationDelay: `${delay}s`, animationDuration: `${0.8 + delay}s` }}
                                    />
                                ))}
                            </div>
                        </div>

                        {/* Midline Symmetry Anchor Row */}
                        <div className={`w-[1px] h-6 transition-colors duration-300 ${isProcessing ? 'bg-amber-500/30' : isListening ? 'bg-red-500/30' : 'bg-cyan-500/30'}`} />

                        {/* Rigid Telemetry Metric Display */}
                        <span className={`font-mono text-[10px] font-bold tracking-[0.2em] transition-colors duration-300 animate-[pulse_2s_ease-in-out_infinite] w-[130px] text-center
                            ${isProcessing ? 'text-amber-500' : isListening ? 'text-red-500' : 'text-cyan-400'}`}>
                            {isProcessing ? "ANALYZING_DATA" : isListening ? "RECORDING_AUDIO" : "SYSTEM_STANDBY"}
                        </span>
                    </div>

                    {/* Integrated Keyboard-Vocal Console Box Layout */}
                    <div className="relative flex items-center group/input w-full">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 font-mono font-bold text-sm text-cyan-500/60 group-hover/input:text-cyan-400 transition-colors duration-300">$&gt;</span>
                        <input
                            type="text"
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                            onKeyDown={handleKeyDown}
                            disabled={isProcessing}
                            placeholder="Awaiting vocal directive or type command..."
                            className="w-full bg-[#030914] border border-cyan-800/60 rounded-lg py-3 pl-10 pr-12 font-mono text-[11px] text-cyan-100 placeholder-cyan-800 focus:outline-none focus:border-cyan-500/60 focus:shadow-[0_0_10px_rgba(6,182,212,0.2)] transition-all duration-300 disabled:opacity-50"
                        />

                        {/* Hardware Link Mic Configuration Button Anchor */}
                        <button
                            onClick={handleMicToggle}
                            disabled={isProcessing}
                            className={`absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-md cursor-pointer border transition-all duration-300 ease-out 
                                ${isProcessing ? 'opacity-50 cursor-not-allowed bg-[#0a1526] text-cyan-800 border-transparent' :
                                    isListening
                                        ? 'bg-red-500/20 text-red-400 border-red-500/50 hover:bg-red-500/30 hover:scale-95 shadow-[0_0_10px_rgba(239,68,68,0.2)]'
                                        : 'bg-cyan-900/20 text-cyan-500 hover:bg-cyan-800/40 hover:text-cyan-300 border-cyan-800/50 hover:border-cyan-500/50'
                                }`}
                        >
                            {isListening ? <Square className="w-4 h-4 fill-current" /> : <Mic className="w-4 h-4" />}
                        </button>
                    </div>
                </div>
            </div>
        </BentoWidget>
    );
}