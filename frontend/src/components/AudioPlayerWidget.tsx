"use client";

import { useState, useEffect } from "react";
import { Music, Disc3, Repeat, SkipBack, Pause, Play, SkipForward, Upload } from "lucide-react";
import BentoWidget from "./BentoWidget";
import { useAppStore } from '../store'; // Import the centralized global state

export default function AudioPlayerWidget() {
    // ==============================================================================
    // GLOBAL STATE HOOKS
    // ==============================================================================
    const setMusicPlayerData = useAppStore((state) => state.setMusicPlayerData);

    // ==============================================================================
    // LOCAL COMPONENT STATE
    // ==============================================================================
    const [audioTrack, setAudioTrack] = useState<{ title: string; artist: string; url: string } | null>(null);
    const [audioPlaying, setAudioPlaying] = useState(false);
    const [audioInstance, setAudioInstance] = useState<HTMLAudioElement | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [isLooping, setIsLooping] = useState(false);
    const [progress, setProgress] = useState(0);
    const [currentTime, setCurrentTime] = useState("0:00");
    const [duration, setDuration] = useState("0:00");

    // ==============================================================================
    // CONTEXT SYNCHRONIZATION
    // Automatically synchronizes the internal component state with the global store
    // so that the Atom Orchestrator is aware of the playback status.
    // ==============================================================================
    useEffect(() => {
        if (!audioTrack) {
            setMusicPlayerData("No audio track currently playing.");
            return;
        }

        const status = audioPlaying
            ? `Playing: ${audioTrack.title} by ${audioTrack.artist}`
            : `Paused: ${audioTrack.title} by ${audioTrack.artist}`;

        setMusicPlayerData(status);
    }, [audioTrack, audioPlaying, setMusicPlayerData]);

    // ==============================================================================
    // AUDIO PROCESSING LOGIC
    // ==============================================================================
    const formatTime = (timeInSeconds: number) => {
        if (isNaN(timeInSeconds)) return "0:00";
        const m = Math.floor(timeInSeconds / 60);
        const s = Math.floor(timeInSeconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    const processAudioFile = (file: File) => {
        if (!file.type.startsWith('audio/')) return;
        if (audioInstance) {
            audioInstance.pause();
            audioInstance.removeAttribute('src');
        }
        if (audioTrack?.url) URL.revokeObjectURL(audioTrack.url);

        const url = URL.createObjectURL(file);
        const newAudio = new Audio(url);
        newAudio.loop = isLooping;

        const cleanFileName = file.name.replace(/\.[^/.]+$/, "");
        let extractedArtist = "Unknown Artist";
        let extractedTitle = cleanFileName;

        if (cleanFileName.includes("-")) {
            const parts = cleanFileName.split("-");
            extractedArtist = parts[0].trim();
            extractedTitle = parts.slice(1).join("-").trim();
        }

        newAudio.addEventListener('loadedmetadata', () => setDuration(formatTime(newAudio.duration)));
        newAudio.addEventListener('timeupdate', () => {
            setCurrentTime(formatTime(newAudio.currentTime));
            setProgress((newAudio.currentTime / newAudio.duration) * 100);
        });
        newAudio.addEventListener('ended', () => {
            if (!newAudio.loop) {
                setAudioPlaying(false);
                setProgress(100);
            }
        });

        setAudioTrack({ title: extractedTitle, artist: extractedArtist, url });
        setAudioPlaying(false);
        setProgress(0);
        setCurrentTime("0:00");
        setDuration("0:00");
        setAudioInstance(newAudio);
    };

    const handleAudioFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) processAudioFile(file);
    };

    const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragging(true); };
    const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragging(false); };
    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault(); e.stopPropagation(); setIsDragging(false);
        const file = e.dataTransfer.files?.[0];
        if (file) processAudioFile(file);
    };

    const toggleAudioPlayback = () => {
        if (!audioInstance) return;
        if (audioPlaying) { audioInstance.pause(); setAudioPlaying(false); }
        else { audioInstance.play().catch(console.error); setAudioPlaying(true); }
    };

    const skipBackward = () => { if (audioInstance) audioInstance.currentTime = Math.max(0, audioInstance.currentTime - 10); };
    const skipForward = () => { if (audioInstance) audioInstance.currentTime = Math.min(audioInstance.duration, audioInstance.currentTime + 10); };

    const toggleLoop = () => {
        const nextLoop = !isLooping;
        if (audioInstance) audioInstance.loop = nextLoop;
        setIsLooping(nextLoop);
    };

    const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
        if (!audioInstance || isNaN(audioInstance.duration)) return;
        const rect = e.currentTarget.getBoundingClientRect();
        let percent = (e.clientX - rect.left) / rect.width;
        percent = Math.max(0, Math.min(1, percent));
        const newTime = percent * audioInstance.duration;
        audioInstance.currentTime = newTime;
        setProgress(percent * 100);
        setCurrentTime(formatTime(newTime));
    };

    // ==============================================================================
    // RENDERER
    // ==============================================================================
    return (
        <BentoWidget title="Audio_Player" icon={Music} colorKey="violet">
            <div
                className={`flex flex-col h-full mt-2 justify-between transition-all duration-300 rounded-xl ${isDragging ? 'bg-violet-500/10 scale-[1.02] ring-2 ring-violet-500/50 p-2 -m-2' : ''}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
            >
                <input type="file" accept="audio/*" id="audio-file-uploader" className="hidden" onChange={handleAudioFileChange} />

                {!audioTrack ? (
                    <label htmlFor="audio-file-uploader" className="mt-auto mb-auto flex flex-col items-center justify-center gap-3 p-4 border-2 border-dashed border-violet-500/30 dark:border-violet-500/20 rounded-xl cursor-pointer hover:border-violet-500 dark:hover:border-violet-400/50 bg-transparent transition-colors duration-300 hover:duration-75 group">
                        <div className="w-10 h-10 rounded-full bg-slate-50 dark:bg-violet-500/10 flex items-center justify-center text-slate-400 dark:text-violet-400 group-hover:text-violet-600 dark:group-hover:text-violet-300 transition-colors duration-300 hover:duration-75">
                            <Music className="w-5 h-5 transition-transform duration-300 hover:duration-75 group-hover:-translate-y-0.5" />
                        </div>
                        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-violet-400/60 group-hover:text-violet-600 dark:group-hover:text-violet-300 text-center leading-relaxed transition-colors duration-300 hover:duration-75">
                            Drag File Here<br />or Click to Upload
                        </span>
                    </label>
                ) : (
                    <div className="flex flex-col h-full justify-between mt-1">
                        <div className="flex items-center gap-3">
                            <div className="relative w-14 h-14 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-600 shadow-lg flex items-center justify-center flex-shrink-0 overflow-hidden select-none">
                                <Disc3 className={`w-8 h-8 text-white/90 transition-transform ${audioPlaying ? 'animate-[spin_4s_linear_infinite]' : ''}`} />
                            </div>
                            <div className="flex flex-col min-w-0 flex-1 overflow-hidden">
                                {audioTrack.title.length > 22 ? (
                                    <div className="w-full overflow-hidden whitespace-nowrap relative after:absolute after:right-0 after:top-0 after:h-full after:w-4 after:bg-gradient-to-l after:from-white dark:after:from-[#0A101A]/10 after:to-transparent">
                                        <div className="animate-news-ticker">
                                            <span className="text-sm font-bold text-slate-800 dark:text-white pr-8">{audioTrack.title}</span>
                                            <span className="text-sm font-bold text-slate-800 dark:text-white pr-8">{audioTrack.title}</span>
                                        </div>
                                    </div>
                                ) : (
                                    <span className="text-sm font-bold text-slate-800 dark:text-white truncate">{audioTrack.title}</span>
                                )}
                                <span className="text-[11px] font-medium text-slate-500/70 dark:text-violet-300/40 truncate mt-0.5 leading-none block">{audioTrack.artist}</span>
                                <span className="text-[9px] font-semibold text-slate-400 dark:text-violet-400/30 uppercase tracking-widest mt-1.5 flex items-center gap-1.5">
                                    <span className={`w-1.5 h-1.5 rounded-full ${audioPlaying ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400/60'}`}></span>
                                    {isLooping ? "In Ripetizione" : "Riproduzione Locale"}
                                </span>
                            </div>
                        </div>

                        <div className="flex flex-col gap-1.5 mt-4">
                            <div className="flex justify-between text-[9px] font-bold text-slate-500 dark:text-violet-400/80 font-mono tracking-wider select-none">
                                <span>{currentTime}</span>
                                <span>{duration}</span>
                            </div>
                            <div className="relative w-full h-2.5 bg-slate-200 dark:bg-violet-950/60 rounded-full cursor-pointer group/bar flex items-center" onClick={handleSeek}>
                                <div className="absolute left-0 h-full bg-violet-600 dark:bg-violet-500 rounded-full pointer-events-none transition-all duration-75 ease-out" style={{ width: `${progress}%` }}>
                                    <div className="absolute -right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full shadow-md opacity-0 group-hover/bar:opacity-100 transition-opacity"></div>
                                </div>
                            </div>
                        </div>

                        <div className="flex items-center justify-between gap-2 mt-auto pt-4 pb-1 w-full px-1">
                            <button onClick={toggleLoop} className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all cursor-pointer border ${isLooping ? 'text-violet-600 dark:text-violet-400 bg-violet-500/10 border-violet-500/30 shadow-[0_0_12px_rgba(139,92,246,0.2)]' : 'text-slate-400 hover:text-slate-600 dark:text-violet-400/40 dark:hover:text-violet-400/70 border-violet-500/30 dark:border-violet-500/10 bg-slate-50 dark:bg-slate-900/20'}`} title={isLooping ? "Disattiva Loop" : "Attiva Loop"}>
                                <Repeat className={`w-4 h-4 ${isLooping ? 'stroke-[2.5px]' : ''}`} />
                            </button>
                            <button onClick={skipBackward} className="p-2 text-slate-400 hover:text-violet-600 dark:text-violet-400/60 dark:hover:text-violet-300 transition-colors cursor-pointer"><SkipBack className="w-5 h-5 fill-current" /></button>
                            <button onClick={toggleAudioPlayback} className="w-12 h-12 rounded-full bg-violet-600 text-white flex items-center justify-center shadow-[0_0_20px_rgba(139,92,246,0.3)] hover:bg-violet-700 hover:scale-105 transition-all duration-300 cursor-pointer flex-shrink-0">
                                {audioPlaying ? <Pause className="w-5 h-5 fill-current" /> : <Play className="w-5 h-5 fill-current ml-1" />}
                            </button>
                            <button onClick={skipForward} className="p-2 text-slate-400 hover:text-violet-600 dark:text-violet-400/60 dark:hover:text-violet-300 transition-colors cursor-pointer"><SkipForward className="w-5 h-5 fill-current" /></button>
                            <label htmlFor="audio-file-uploader" className="w-9 h-9 rounded-xl flex items-center justify-center border text-slate-400 hover:text-slate-600 dark:text-violet-400/40 dark:hover:text-violet-400/70 border-violet-500/30 dark:border-violet-500/10 bg-slate-50 dark:bg-slate-900/20 hover:bg-slate-100 dark:hover:bg-slate-900/40 transition-colors duration-300 hover:duration-75 cursor-pointer shadow-none group" title="Cambia traccia audio">
                                <Upload className="w-4 h-4 transition-colors group-hover:text-violet-600 dark:group-hover:text-violet-400" />
                            </label>
                        </div>
                    </div>
                )}
            </div>
        </BentoWidget>
    );
}