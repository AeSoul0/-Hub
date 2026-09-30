/**
 * @file frontend/src/components/widgets/CoreOrchestratorWidget.tsx
 * @description Core orchestrator widget for text and voice interactions.
 *
 * Provides the primary user interface for:
 * - microphone capture;
 * - voice command submission;
 * - text command submission;
 * - backend response handling;
 * - live dashboard context forwarding.
 *
 * Transport is centralized through the shared API client. Multipart requests
 * intentionally do not set Content-Type manually so the browser can attach
 * the correct multipart boundary.
 */

"use client";

import { useRef, useState } from "react";
import {
    Activity,
    Cpu,
    Loader2,
    Mic,
    Square,
    Terminal,
    Wifi,
} from "lucide-react";
import BentoWidget from "@/components/widgets/BentoWidget";
import { fetchApi } from "@/lib/api/client";
import { useAppStore } from "../../store/index";

// ==============================================================================
// COMPATIBILITY AUTHENTICATION LAYER
// ==============================================================================

/**
 * Returns the legacy session header used by the current backend contract.
 *
 * P2 will replace client-managed session identifiers with secure cookie-based
 * authentication and server-side principal resolution.
 */
const getAuthHeaders = (): Record<string, string> => {
    let sessionId = "";

    if (typeof window !== "undefined") {
        sessionId = localStorage.getItem("aehub_session_id") || "";

        if (!sessionId) {
            sessionId =
                typeof crypto !== "undefined" && crypto.randomUUID
                    ? crypto.randomUUID()
                    : Math.random().toString(36).slice(2);

            localStorage.setItem("aehub_session_id", sessionId);
        }
    }

    return {
        "X-Session-ID": sessionId,
    };
};

// ==============================================================================
// COMPONENT
// ==============================================================================

export default function CoreOrchestratorWidget() {
    const [isListening, setIsListening] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [inputText, setInputText] = useState("");

    const liveWeatherData = useAppStore((state) => state.weatherData);
    const liveMediaStatus = useAppStore(
        (state) => state.mediaConverterStatus,
    );
    const liveMusicData = useAppStore((state) => state.musicPlayerData);
    const liveAcademicData = useAppStore(
        (state) => state.academicData,
    );

    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<BlobPart[]>([]);

    // ==========================================================================
    // LIVE DASHBOARD CONTEXT
    // ==========================================================================

    /**
     * Serializes the current dashboard telemetry for backend context.
     */
    const getLiveSystemContext = (): string => {
        const dashboardState = {
            systemTime: new Date().toLocaleTimeString("it-IT"),
            weatherWidgetTelemetry: liveWeatherData,
            mediaConverterTelemetry: liveMediaStatus,
            musicPlayerTelemetry: liveMusicData,
            academicModuleTelemetry: liveAcademicData,
        };

        return JSON.stringify(dashboardState, null, 2);
    };

    // ==========================================================================
    // BACKEND RESPONSE HANDLING
    // ==========================================================================

    /**
     * Validates and consumes an orchestrator response.
     */
    const handleBackendResponse = async (response: Response) => {
        if (!response.ok) {
            if (response.status === 401) {
                throw new Error("401 Unauthorized");
            }

            throw new Error(
                `Backend orchestration request failed: ${response.status}`,
            );
        }

        const data = await response.json();

        setInputText("");

        if (data.audio_base64) {
            const audio = new Audio(
                `data:audio/mp3;base64,${data.audio_base64}`,
            );
            await audio.play();
        }
    };

    // ==========================================================================
    // VOICE INPUT PIPELINE
    // ==========================================================================

    /**
     * Sends recorded audio to the orchestrator endpoint.
     */
    const sendVoiceToBackend = async (blob: Blob) => {
        setIsProcessing(true);
        setInputText("Compressing audio payload for orchestration...");

        try {
            const formData = new FormData();
            formData.append("file", blob, "voice_command.webm");
            formData.append("ui_context", getLiveSystemContext());

            const response = await fetchApi(
                "/api/orchestrator/listen",
                {
                    method: "POST",
                    headers: getAuthHeaders(),
                    body: formData,
                    credentials: "include",
                },
            );

            await handleBackendResponse(response);
        } catch (error: unknown) {
            console.error("Voice orchestration request failed:", error);
            setInputText(
                "CRITICAL: Gateway synchronization failed.",
            );
        } finally {
            setIsProcessing(false);
        }
    };

    /**
     * Starts browser microphone capture.
     */
    const startRecording = async () => {
        try {
            setInputText("Initializing microphone input...");

            if (
                typeof navigator === "undefined" ||
                !navigator.mediaDevices?.getUserMedia
            ) {
                setInputText("MIC NOT SUPPORTED ON THIS DEVICE");
                return;
            }

            const stream =
                await navigator.mediaDevices.getUserMedia({
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
            setInputText("Recording...");
        } catch (error: unknown) {
            console.error("Microphone access failed:", error);
            setInputText("MIC ACCESS DENIED OR UNSUPPORTED DEVICE");
        }
    };

    /**
     * Stops microphone capture and triggers upload.
     */
    const stopRecording = () => {
        const recorder = mediaRecorderRef.current;

        if (recorder && recorder.state !== "inactive") {
            recorder.stop();
        }

        setIsListening(false);
    };

    // ==========================================================================
    // TEXT INPUT PIPELINE
    // ==========================================================================

    /**
     * Sends a textual directive to the orchestrator.
     */
    const sendTextToBackend = async (text: string) => {
        setIsProcessing(true);
        setInputText("TRANSMITTING TEXT DIRECTIVE...");

        try {
            const formData = new FormData();
            formData.append("text", text);
            formData.append("ui_context", getLiveSystemContext());

            const response = await fetchApi(
                "/api/orchestrator/ask",
                {
                    method: "POST",
                    headers: getAuthHeaders(),
                    body: formData,
                    credentials: "include",
                },
            );

            await handleBackendResponse(response);
        } catch (error: unknown) {
            console.error("Text orchestration request failed:", error);
            setInputText(
                "CRITICAL: Gateway synchronization failed.",
            );
        } finally {
            setIsProcessing(false);
        }
    };

    /**
     * Dispatches text submission when Enter is pressed.
     */
    const handleKeyDown = (
        event: React.KeyboardEvent<HTMLInputElement>,
    ) => {
        if (event.key !== "Enter") {
            return;
        }

        const value = inputText.trim();

        if (!value || isProcessing) {
            return;
        }

        void sendTextToBackend(value);
    };

    /**
     * Toggles microphone capture.
     */
    const handleMicToggle = () => {
        if (isProcessing) {
            return;
        }

        if (isListening) {
            stopRecording();
        } else {
            void startRecording();
        }
    };

    // ==========================================================================
    // RENDERING
    // ==========================================================================

    return (
        <BentoWidget
            title="ATOM_CORE"
            icon={Terminal}
            colorKey="cyan"
            colSpan={2}
        >
            <div className="relative flex flex-col justify-between h-full w-full mt-2 rounded-xl overflow-hidden bg-gradient-to-br from-[#020813] to-[#0a1122] border border-cyan-900/50 p-4 shadow-[inset_0_0_40px_rgba(6,182,212,0.03)]">
                <div className="absolute inset-0 bg-[linear-gradient(rgba(6,182,212,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(6,182,212,0.05)_1px,transparent_1px)] bg-[size:16px_16px] pointer-events-none opacity-50" />

                <div className="relative flex justify-between items-center w-full mb-4 font-mono text-[9px] text-cyan-500/60 uppercase tracking-widest z-10">
                    <div className="flex items-center gap-2">
                        <Cpu className="w-3 h-3 text-cyan-600" />
                        <span>SYS.CORE // ATOM_PROCESSOR</span>
                    </div>

                    <div className="flex items-center gap-2">
                        <span>UPLINK: SECURE_LINK</span>
                        <Wifi className="w-3 h-3 text-cyan-600" />
                    </div>
                </div>

                <div className="relative flex flex-col gap-4 z-10 w-full mt-auto">
                    <div className="flex items-center justify-center gap-6 bg-[#040d1a]/80 border border-cyan-500/20 rounded-lg p-3 backdrop-blur-md">
                        <div className="flex items-center gap-4">
                            <div
                                className={`relative flex items-center justify-center w-8 h-8 rounded-md border ${
                                    isProcessing
                                        ? "bg-amber-500/10 border-amber-500/50"
                                        : isListening
                                          ? "bg-red-500/10 border-red-500/50"
                                          : "bg-cyan-500/10 border-cyan-500/30"
                                }`}
                            >
                                <div
                                    className={`absolute inset-0 rounded-md animate-ping opacity-40 ${
                                        isListening
                                            ? "bg-red-500/30"
                                            : isProcessing
                                              ? "bg-amber-500/30"
                                              : "bg-cyan-500/20"
                                    }`}
                                />

                                {isProcessing ? (
                                    <Loader2 className="w-4 h-4 text-amber-500 animate-spin" />
                                ) : (
                                    <Activity
                                        className={`w-4 h-4 animate-pulse ${
                                            isListening
                                                ? "text-red-500"
                                                : "text-cyan-400"
                                        }`}
                                    />
                                )}
                            </div>

                            <div className="flex items-end gap-[2px] h-5">
                                {[0.1, 0.4, 0.2, 0.6, 0.3, 0.5].map(
                                    (delay, index) => (
                                        <div
                                            key={index}
                                            className={`w-[3px] rounded-sm animate-[wave-pulse_1s_ease-in-out_infinite] ${
                                                isListening
                                                    ? "bg-red-500"
                                                    : "bg-cyan-500/70"
                                            }`}
                                            style={{
                                                animationDelay: `${delay}s`,
                                                animationDuration: `${
                                                    0.8 + delay
                                                }s`,
                                            }}
                                        />
                                    ),
                                )}
                            </div>
                        </div>

                        <div
                            className={`w-[1px] h-6 ${
                                isProcessing
                                    ? "bg-amber-500/30"
                                    : isListening
                                      ? "bg-red-500/30"
                                      : "bg-cyan-500/30"
                            }`}
                        />

                        <span
                            className={`font-mono text-[10px] font-bold tracking-[0.2em] w-[130px] text-center ${
                                isProcessing
                                    ? "text-amber-500"
                                    : isListening
                                      ? "text-red-500"
                                      : "text-cyan-400"
                            }`}
                        >
                            {isProcessing
                                ? "ANALYZING_DATA"
                                : isListening
                                  ? "RECORDING_AUDIO"
                                  : "SYSTEM_STANDBY"}
                        </span>
                    </div>

                    <div className="relative flex items-center group/input w-full">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 font-mono font-bold text-sm text-cyan-500/60">
                            $&gt;
                        </span>

                        <input
                            type="text"
                            value={inputText}
                            onChange={(event) =>
                                setInputText(event.target.value)
                            }
                            onKeyDown={handleKeyDown}
                            disabled={isProcessing}
                            placeholder="Awaiting vocal directive or type command..."
                            className="w-full bg-[#030914] border border-cyan-800/60 rounded-lg py-3 pl-10 pr-12 font-mono text-[11px] text-cyan-100 placeholder-cyan-800 focus:outline-none focus:border-cyan-500/60 disabled:opacity-50"
                        />

                        <button
                            type="button"
                            onClick={handleMicToggle}
                            disabled={isProcessing}
                            aria-label={
                                isListening
                                    ? "Stop voice recording"
                                    : "Start voice recording"
                            }
                            className={`absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-md border transition-all ${
                                isProcessing
                                    ? "opacity-50 cursor-not-allowed"
                                    : isListening
                                      ? "bg-red-500/20 text-red-400 border-red-500/50"
                                      : "bg-cyan-900/20 text-cyan-500 border-cyan-800/50"
                            }`}
                        >
                            {isListening ? (
                                <Square className="w-4 h-4 fill-current" />
                            ) : (
                                <Mic className="w-4 h-4" />
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </BentoWidget>
    );
}
