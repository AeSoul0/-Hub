"use client";

import { useEffect, useState } from "react";
import { Cloud, Play, GraduationCap, Activity, LayoutDashboard, Sun, Moon, Thermometer, Wind, Droplets, Mic, Terminal, Search, Download, Lock, CheckCircle2, Sunrise, Gauge, ThermometerSun, Umbrella, LogOut, Music, Pause, Disc3, SkipBack, SkipForward, Repeat, Upload } from "lucide-react"; 
import BentoWidget from '../components/BentoWidget';

interface WeatherData {
  city: string;
  temperature: string;
  condition: string;
  tempMax: string;
  tempMin: string;
  wind: string;
  humidity: string;
  feelsLike: string;
  sunrise: string;
  pressure: string;
  willRain: boolean;
}

export default function Home() {
  // Environmental Global Interfaces States
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [backendStatus, setBackendStatus] = useState("Connecting...");
  const [isDarkMode, setIsDarkMode] = useState(true);

  // Sub-modules Operations Handlers States
  const [mediaQuery, setMediaQuery] = useState("");
  const [mediaStatus, setMediaStatus] = useState<"idle" | "searching" | "downloading" | "done">("idle");

  // Academic States mapping database payloads
  const [academicLogged, setAcademicLogged] = useState(false);
  const [academicLoading, setAcademicLoading] = useState(false);
  const [academicData, setAcademicData] = useState({ gpa: 0, exams: 0, cfu: 0 });

  // --- REAL AUDIO PLAYER STATES & HANDLERS ---
  const [audioTrack, setAudioTrack] = useState<{ title: string; artist: string; url: string } | null>(null);
  const [audioPlaying, setAudioPlaying] = useState(false);
  const [audioInstance, setAudioInstance] = useState<HTMLAudioElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isLooping, setIsLooping] = useState(false);

  // Stati per la timeline temporale e barra di progressione
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrentTime] = useState("0:00");
  const [duration, setDuration] = useState("0:00");

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
      audioInstance.removeAttribute('src'); // Rilascia le risorse di memoria del browser
    }
    if (audioTrack?.url) URL.revokeObjectURL(audioTrack.url);

    const url = URL.createObjectURL(file);
    const newAudio = new Audio(url);

    // Configura la proprietà loop nativa dell'oggetto Audio HTML5
    newAudio.loop = isLooping;

    // Rimuove l'estensione finale dal nome del file (.mp3, .wav, ecc.)
    const cleanFileName = file.name.replace(/\.[^/.]+$/, "");

    // Prova a separare Artista e Titolo se è presente il trattino "-"
    let extractedArtist = "Unknown Artist";
    let extractedTitle = cleanFileName;

    if (cleanFileName.includes("-")) {
      const parts = cleanFileName.split("-");
      extractedArtist = parts[0].trim();
      // Unisce il resto nel caso ci fossero più trattini nel titolo
      extractedTitle = parts.slice(1).join("-").trim();
    }

    // Eventi di ascolto asincroni per tracciare la riproduzione in tempo reale
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

  // Drag & Drop Handlers globali per il perimetro del widget
  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragging(true); };
  const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragging(false); };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) processAudioFile(file);
  };

  // Controlli del player audio
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

  // Gestore del click sulla barra temporale (Salto istantaneo ultra-reattivo)
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

  useEffect(() => {
    setIsDarkMode(document.documentElement.classList.contains('dark'));
  }, []);

  const toggleTheme = () => {
    const overrideTransitions = document.createElement('style');
    overrideTransitions.type = 'text/css';
    overrideTransitions.appendChild(document.createTextNode(`
      *:not(.theme-transition-keep) { transition: none !important; }
    `));
    document.head.appendChild(overrideTransitions);

    const isDark = document.documentElement.classList.contains('dark');
    if (isDark) {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
      setIsDarkMode(false);
    } else {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
      setIsDarkMode(true);
    }

    window.getComputedStyle(overrideTransitions).opacity;
    document.head.removeChild(overrideTransitions);
  };

  // Check Academic Data Cached (Real-Time Sync on startup initialization)
  useEffect(() => {
    async function checkAcademicStatus() {
      try {
        const res = await fetch("http://127.0.0.1:3002/api/academic/status");
        if (res.ok) {
          const result = await res.json();
          if (result.status === "success") {
            setAcademicData(result.data);
            setAcademicLogged(true);
          }
        }
      } catch (e) {
        console.log("Academic cache check failed bounds");
      }
    }
    checkAcademicStatus();
  }, []);

  // Weather and Backend Status Polling Loop
  useEffect(() => {
    fetch("http://127.0.0.1:3002/")
      .then((res) => res.json())
      .then((data) => setBackendStatus(data.status))
      .catch(() => setBackendStatus("Offline"));

    async function fetchWeather() {
      try {
        const res = await fetch("https://api.open-meteo.com/v1/forecast?latitude=41.9028&longitude=12.4964&current=temperature_2m,relative_humidity_2m,apparent_temperature,surface_pressure,weather_code,wind_speed_10m&hourly=weather_code&daily=temperature_2m_max,temperature_2m_min,sunrise&timezone=auto");
        const data = await res.json();

        const getCondition = (code: number) => {
          if (code >= 1 && code <= 3) return "Cloudy";
          if (code >= 45 && code <= 48) return "Fog";
          if (code >= 51 && code <= 67) return "Rain";
          if (code >= 71 && code <= 77) return "Snow";
          if (code >= 95) return "Thunderstorm";
          return "Clear";
        };

        const currentHour = new Date().getHours();
        const startIndex = data.hourly.time.findIndex((t: string) => new Date(t).getHours() === currentHour);
        let rainExpected = false;

        if (startIndex !== -1) {
          for (let i = 1; i <= 4; i++) {
            const code = data.hourly.weather_code[startIndex + i];
            if ((code >= 51 && code <= 67) || (code >= 80 && code <= 99)) {
              rainExpected = true;
              break;
            }
          }
        }

        const sunriseTime = new Date(data.daily.sunrise[0]).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        setWeather({
          city: "Rome",
          temperature: `${Math.round(data.current.temperature_2m)}°`,
          condition: getCondition(data.current.weather_code),
          tempMax: `${Math.round(data.daily.temperature_2m_max[0])}°`,
          tempMin: `${Math.round(data.daily.temperature_2m_min[0])}°`,
          wind: `${Math.round(data.current.wind_speed_10m)} km/h`,
          humidity: `${data.current.relative_humidity_2m}%`,
          feelsLike: `${Math.round(data.current.apparent_temperature)}°`,
          pressure: `${Math.round(data.current.surface_pressure)} hPa`,
          sunrise: sunriseTime,
          willRain: rainExpected
        });
      } catch (err) {
        console.error("Telemetry fetch fault:", err);
      }
    }

    fetchWeather();
    const telemetryInterval = setInterval(fetchWeather, 30000);
    return () => clearInterval(telemetryInterval);
  }, []);

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

  // Trigger SPID Authentication lifecycle
  const handleSpidSync = async (e: React.MouseEvent) => {
    e.preventDefault();
    setAcademicLoading(true);
    try {
      const res = await fetch("http://127.0.0.1:3002/api/academic/login", { method: "POST" });
      if (res.ok) {
        const result = await res.json();
        setAcademicData(result.data);
        setAcademicLogged(true);
      } else {
        alert("SPID Authentication Timeout or Failed.");
      }
    } catch (err) {
      alert("Backend Core Engine Offline.");
    } finally {
      setAcademicLoading(false);
    }
  };

  // Clear cached data and break automation state binds
  const handleAcademicDisconnect = async (e: React.MouseEvent) => {
    e.preventDefault();
    try {
      const res = await fetch("http://127.0.0.1:3002/api/academic/logout", { method: "POST" });
      if (res.ok) {
        setAcademicLogged(false);
        setAcademicData({ gpa: 0, exams: 0, cfu: 0 });
      }
    } catch (err) {
      console.error("Purge session request failed network thresholds:", err);
    }
  };

  return (
    <div className="relative p-6 z-0 min-h-screen overflow-hidden">

      <style dangerouslySetInnerHTML={{
        __html: `
        @keyframes agent-linked-pulse { 0%, 100% { opacity: 0.5; } 50% { opacity: 1; text-shadow: 0 0 12px rgba(6, 182, 212, 0.6); } }
        @keyframes wave-pulse { 0%, 100% { height: 4px; } 50% { height: 20px; } }
        .holographic-space { background-image: radial-gradient(circle at 50% 0%, rgba(15, 118, 110, 0.04) 0%, transparent 60%), radial-gradient(circle at 100% 100%, rgba(15, 118, 110, 0.03) 0%, transparent 50%); }
        .dark .holographic-space { background-image: radial-gradient(circle at 50% 0%, rgba(6, 182, 212, 0.08) 0%, transparent 60%), radial-gradient(circle at 100% 100%, rgba(6, 182, 212, 0.05) 0%, transparent 50%); }
        .depth-mesh { background-size: 60px 60px; background-image: linear-gradient(rgba(15, 118, 110, 0.02) 1px, transparent 1px); transform: perspective(500px) rotateX(60deg); transform-origin: top center; }
        .dark .depth-mesh { background-image: linear-gradient(rgba(6, 182, 212, 0.03) 1px, transparent 1px); }
      `}} />

      <div className="fixed inset-0 holographic-space pointer-events-none -z-20 transition-colors duration-700" />
      <div className="fixed top-0 left-0 w-full h-[200vh] depth-mesh pointer-events-none -z-20 opacity-50 transition-colors duration-700" />

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

      <main className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 auto-rows-[240px] items-stretch relative z-10">

        {/* ENHANCED WEATHER CARD */}
        <BentoWidget
          title="Atmosphere"
          icon={Cloud}
          colorKey="cyan"
          colSpan={2}
          textSize="text-6xl"
          isLoading={!weather}
          mainText={weather?.temperature}
          subTextLeft={weather?.city}
          subTextRight={weather?.condition}
        >
          {weather && (
            <div className="w-full mt-auto relative">
              {weather.willRain && (
                <div className="absolute -top-12 right-0 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-[9px] font-bold uppercase tracking-widest text-cyan-600 dark:text-cyan-400 animate-pulse">
                  <Umbrella className="w-3 h-3" />
                  Rain Expected
                </div>
              )}

              <div className="pt-4 mt-3 border-t border-slate-200/70 dark:border-white/10 grid grid-cols-3 gap-2 text-[10px] sm:text-[11px] font-bold uppercase tracking-widest text-slate-500 dark:text-cyan-600/70">                <div className="flex flex-col gap-3 items-start">
                  <span className="flex items-center gap-2"><Thermometer className="w-3.5 h-3.5 text-cyan-600/60" /> {weather.tempMin}/{weather.tempMax}</span>
                  <span className="flex items-center gap-2"><Wind className="w-3.5 h-3.5 text-cyan-600/60" /> {weather.wind}</span>
                </div>
                <div className="flex flex-col gap-3 items-start mx-auto">
                  <span className="flex items-center gap-2"><ThermometerSun className="w-3.5 h-3.5 text-cyan-600/60" /> Feels: {weather.feelsLike}</span>
                  <span className="flex items-center gap-2"><Droplets className="w-3.5 h-3.5 text-cyan-600/60" /> {weather.humidity}</span>
                </div>
                <div className="flex flex-col gap-3 items-start ml-auto">
                  <span className="flex items-center gap-2"><Sunrise className="w-3.5 h-3.5 text-cyan-600/60" /> Rise: {weather.sunrise}</span>
                  <span className="flex items-center gap-2"><Gauge className="w-3.5 h-3.5 text-cyan-600/60" /> {weather.pressure}</span>
                </div>
              </div>
            </div>
          )}
        </BentoWidget>

        {/* ACADEMIC CARD (WITH DISCONNECT FIXED SYMMETRY GRID & FAST ACTION HOVER PILL) */}
        <BentoWidget
          title="Academic"
          icon={GraduationCap}
          colorKey="indigo"
          isLoading={academicLoading}
        >
          {academicLogged ? (
            <div className="flex flex-col h-full mt-2">
              <div className="text-5xl font-[family-name:var(--font-quicksand)] font-semibold text-slate-900 dark:text-white">{academicData.gpa}</div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-indigo-600/60 mt-1">Average GPA</div>

              {/* FIXED SYMMETRY GRID: Using exact 3-column architecture mimicking the weather card layout alignment metrics */}
              <div className="mt-auto pt-4 border-t border-slate-200/70 dark:border-white/10 grid grid-cols-3 gap-2 text-[10px] sm:text-[11px] font-bold uppercase tracking-widest text-slate-500 dark:text-indigo-400/60 items-center">
                {/* Column 1: Aligned Start */}
                <div className="flex flex-col justify-center items-start">
                  <span>Exams: {academicData.exams}</span>
                </div>

                {/* Column 2: Centered in place */}
                <div className="flex flex-col justify-center items-start mx-auto">
                  <span>CFU: {academicData.cfu}</span>
                </div>

                {/* Column 3: Aligned End - Interactive Hybrid Status Toggle Button */}
                <div className="flex flex-col justify-center items-end ml-auto">
                  <button
                    onClick={handleAcademicDisconnect}
                    className="group/logout px-3 py-1.5 h-7 text-[10px] font-bold tracking-wider rounded-lg border border-slate-200/70 dark:border-white/10 bg-slate-50 dark:bg-white/5 text-indigo-600 dark:text-indigo-400 hover:text-red-500 hover:bg-red-50 dark:hover:text-rose-400 dark:hover:bg-rose-500/10 dark:hover:border-rose-500/20 uppercase transition-all duration-100 ease-out flex items-center justify-center gap-1.5 cursor-pointer w-[92px]"
                  >
                    {/* Default Synced Layout view layers */}
                    <CheckCircle2 className="w-3.5 h-3.5 block group-hover/logout:hidden transition-none" />
                    <span className="block group-hover/logout:hidden tracking-widest transition-none">Synced</span>

                    {/* Active hover overlay morphing state views */}
                    <LogOut className="w-3.5 h-3.5 hidden group-hover/logout:block transition-none" />
                    <span className="hidden group-hover/logout:block tracking-widest transition-none">Reset</span>
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-col h-full justify-between">
              <p className="text-[10px] uppercase font-bold tracking-widest text-slate-400 dark:text-indigo-400/60 mt-2 text-center leading-relaxed">
                Action Required:<br />Manual SPID Authentication
              </p>

              <button
                onClick={handleSpidSync}
                className="mt-auto w-full bg-slate-100 hover:bg-indigo-50 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-indigo-700 dark:text-indigo-400 text-[10px] font-bold uppercase tracking-[0.2em] py-3 rounded-lg transition-colors border border-slate-200 dark:border-indigo-500/20 flex items-center justify-center gap-2"
              >
                <Lock className="w-3.5 h-3.5" />
                INITIATE SYNC
              </button>
            </div>
          )}
        </BentoWidget>

        {/* MEDIA SYNC CARD */}
        <BentoWidget
          title="Mp3 - Extractor"
          icon={Play}
          colorKey="rose"
        >
          <div className="flex flex-col h-full mt-2 justify-between">
            <form onSubmit={handleMediaDownload} className="relative flex items-center group/search mt-auto mb-3">
              <Search className="absolute left-2.5 w-3.5 h-3.5 text-slate-400 dark:text-rose-500/50 group-hover/search:text-rose-600 dark:group-hover/search:text-rose-400 transition-colors" />
              <input
                value={mediaQuery}
                onChange={(e) => setMediaQuery(e.target.value)}
                disabled={mediaStatus !== "idle"}
                type="text"
                placeholder="Artist - Title..."
                className="w-full bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-rose-500/20 rounded-lg py-2 pl-8 pr-10 text-[11px] font-bold text-slate-800 dark:text-rose-50 placeholder-slate-400 dark:placeholder-rose-700/60 focus:outline-none focus:border-rose-400 transition-colors disabled:opacity-50"
              />
              <button disabled={mediaStatus !== "idle" || !mediaQuery} type="submit" className="absolute right-1.5 p-1.5 rounded-md bg-slate-200 hover:bg-rose-100 dark:bg-rose-500/10 dark:hover:bg-rose-500/20 text-slate-500 hover:text-rose-600 dark:text-rose-400 disabled:opacity-50 transition-colors">
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

        <BentoWidget
          variant="slot"
          title={<>Module<br />Alpha</>}
          icon={LayoutDashboard}
          colorKey="cyan"
        />

        <BentoWidget
          title="Core_Orchestrator"
          icon={Terminal}
          colorKey="cyan"
          colSpan={2}
        >
          <div className="flex flex-col justify-end h-full gap-4 mt-2">
            <div className="flex items-center justify-between bg-white/50 dark:bg-white/[0.02] border border-slate-200/70 dark:border-white/10 rounded-2xl p-3.5 backdrop-blur-lg transition-colors duration-300 ease-out">              <div className="flex items-center gap-4">
                <div className="relative flex items-center justify-center w-8 h-8 rounded-full bg-cyan-500/10 border border-cyan-500/20 shadow-[0_0_15px_rgba(6,182,212,0.1)]">
                  <div className="absolute inset-0 rounded-full bg-cyan-500/20 animate-ping opacity-50" />
                  <Activity className="w-4 h-4 text-cyan-600 dark:text-cyan-400 animate-pulse" />
                </div>
                <div className="flex items-end gap-1 h-5">
                  <div className="w-[3px] bg-cyan-600/40 dark:bg-cyan-500/50 rounded-full animate-[wave-pulse_1s_ease-in-out_infinite]" style={{ animationDelay: '0.1s' }} />
                  <div className="w-[3px] bg-cyan-600/80 dark:bg-cyan-400 rounded-full animate-[wave-pulse_1.2s_ease-in-out_infinite]" style={{ animationDelay: '0.4s' }} />
                  <div className="w-[3px] bg-cyan-500 dark:bg-cyan-300 rounded-full animate-[wave-pulse_0.9s_ease-in-out_infinite]" style={{ animationDelay: '0.2s' }} />
                  <div className="w-[3px] bg-cyan-600/60 dark:bg-cyan-500/70 rounded-full animate-[wave-pulse_1.1s_ease-in-out_infinite]" style={{ animationDelay: '0.6s' }} />
                  <div className="w-[3px] bg-cyan-400 dark:bg-cyan-200 rounded-full animate-[wave-pulse_1.3s_ease-in-out_infinite]" style={{ animationDelay: '0.3s' }} />
                </div>
              </div>
              <span className="text-[10px] font-bold tracking-[0.2em] text-cyan-700 dark:text-cyan-400 animate-[agent-linked-pulse_2s_ease-in-out_infinite]">LINK_ACTIVE</span>
            </div>

            <div className="relative flex items-center group/input">
              <span className="absolute left-4 font-bold text-sm text-cyan-600/50 dark:text-cyan-400/50 group-hover/input:text-cyan-600 dark:group-hover/input:text-cyan-400 transition-colors duration-300 ease-out">&gt;</span>
              <input
                type="text"
                disabled
                placeholder="Awaiting vocal/text directive..."
                className="w-full bg-white dark:bg-[#0A101A]/40 border border-slate-200/70 dark:border-white/10 rounded-xl py-3 pl-9 pr-12 text-xs font-bold text-slate-800 dark:text-cyan-50 placeholder-slate-400/80 dark:placeholder-cyan-700 focus:outline-none cursor-not-allowed shadow-[inset_0_2px_10px_rgba(0,0,0,0.02)] transition-colors duration-300 ease-out"
              />
              <button disabled className="absolute right-2.5 p-2 rounded-lg bg-slate-100 dark:bg-cyan-500/10 text-slate-400 dark:text-cyan-500/60 cursor-not-allowed border border-slate-200/80 dark:border-transparent transition-all duration-300 ease-out">
                <Mic className="w-4 h-4" />
              </button>
            </div>
          </div>
        </BentoWidget>

        {/* REAL AUDIO PLAYER WIDGET - SYMMETRIC BENTO EDITION */}
        <BentoWidget
          title="Audio_Player"
          icon={Music}
          colorKey="violet"
        >
          {/* Stile CSS Inline per l'effetto telegiornale infinito hardware-accelerated */}
          <style dangerouslySetInnerHTML={{
            __html: `
            @keyframes newsTicker {
              0% { transform: translate3d(0, 0, 0); }
              100% { transform: translate3d(-50%, 0, 0); }
            }
            .animate-news-ticker {
              display: inline-block;
              white-space: nowrap;
              animation: newsTicker 12s linear infinite;
            }
            .animate-news-ticker:hover {
              animation-play-state: paused;
            }
          `}} />

          {/* Area Sensibile al Drag & Drop */}
          <div
            className={`flex flex-col h-full mt-2 justify-between transition-all duration-300 rounded-xl ${isDragging ? 'bg-violet-500/10 scale-[1.02] ring-2 ring-violet-500/50 p-2 -m-2' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <input type="file" accept="audio/*" id="audio-file-uploader" className="hidden" onChange={handleAudioFileChange} />

            {!audioTrack ? (
              /* STATO VUOTO (Design Premium: nessuno sfarfallio di sfondo, si illumina solo il tratto) */
              <label
                htmlFor="audio-file-uploader"
                className="mt-auto mb-auto flex flex-col items-center justify-center gap-3 p-4 border-2 border-dashed border-slate-200 dark:border-violet-500/20 rounded-xl cursor-pointer hover:border-violet-500/60 dark:hover:border-violet-400/50 bg-transparent transition-colors duration-300 group"
              >
                <div className="w-10 h-10 rounded-full bg-slate-50 dark:bg-violet-500/10 flex items-center justify-center text-slate-400 dark:text-violet-400 group-hover:text-violet-600 dark:group-hover:text-violet-300 transition-colors duration-300">
                  <Music className="w-5 h-5 transition-transform duration-300 group-hover:-translate-y-0.5" />
                </div>
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-violet-400/60 group-hover:text-violet-600 dark:group-hover:text-violet-300 text-center leading-relaxed transition-colors duration-300">
                  Trascina il file qui<br />o Clicca per caricare
                </span>
              </label>
            ) : (
              /* STATO PLAYER ATTIVO */
              <div className="flex flex-col h-full justify-between mt-1">

                {/* Info Traccia e Copertina */}
                <div className="flex items-center gap-3">
                  <div className="relative w-14 h-14 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-600 shadow-lg flex items-center justify-center flex-shrink-0 overflow-hidden select-none">
                    <Disc3 className={`w-8 h-8 text-white/90 transition-transform ${audioPlaying ? 'animate-[spin_4s_linear_infinite]' : ''}`} />
                  </div>

                  {/* Sezione Titolo e Artista con logica Telegiornale (Marquee) */}
                  <div className="flex flex-col min-w-0 flex-1 overflow-hidden">
                    {audioTrack.title.length > 22 ? (
                      /* Titolo scorrevole stile Telegiornale se lungo */
                      <div className="w-full overflow-hidden whitespace-nowrap relative after:absolute after:right-0 after:top-0 after:h-full after:w-4 after:bg-gradient-to-l after:from-white dark:after:from-[#0A101A]/10 after:to-transparent">
                        <div className="animate-news-ticker">
                          <span className="text-sm font-bold text-slate-800 dark:text-white pr-8">{audioTrack.title}</span>
                          <span className="text-sm font-bold text-slate-800 dark:text-white pr-8">{audioTrack.title}</span>
                        </div>
                      </div>
                    ) : (
                      /* Titolo statico se corto */
                      <span className="text-sm font-bold text-slate-800 dark:text-white truncate">{audioTrack.title}</span>
                    )}

                    {/* Sottotitolo con il nome dell'Artista (trasparente ma leggibile) */}
                    <span className="text-[11px] font-medium text-slate-500/70 dark:text-violet-300/40 truncate mt-0.5 leading-none block">
                      {audioTrack.artist}
                    </span>

                    <span className="text-[9px] font-semibold text-slate-400 dark:text-violet-400/30 uppercase tracking-widest mt-1.5 flex items-center gap-1.5">
                      <span className={`w-1.5 h-1.5 rounded-full ${audioPlaying ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400/60'}`}></span>
                      {isLooping ? "In Ripetizione" : "Riproduzione Locale"}
                    </span>
                  </div>
                </div>

                {/* Timeline e Barra di progressione cliccabile */}
                <div className="flex flex-col gap-1.5 mt-4">
                  <div className="flex justify-between text-[9px] font-bold text-slate-500 dark:text-violet-400/80 font-mono tracking-wider select-none">
                    <span>{currentTime}</span>
                    <span>{duration}</span>
                  </div>

                  <div
                    className="relative w-full h-2.5 bg-slate-200 dark:bg-violet-950/60 rounded-full cursor-pointer group/bar flex items-center"
                    onClick={handleSeek}
                  >
                    <div
                      className="absolute left-0 h-full bg-violet-600 dark:bg-violet-500 rounded-full pointer-events-none transition-all duration-75 ease-out"
                      style={{ width: `${progress}%` }}
                    >
                      <div className="absolute -right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full shadow-md opacity-0 group-hover/bar:opacity-100 transition-opacity"></div>
                    </div>
                  </div>
                </div>

                {/* Deck Controlli Perfettamente Simmetrico (5 Colonne Bilanciate) */}
                <div className="flex items-center justify-between gap-2 mt-auto pt-4 pb-1 w-full px-1">

                  {/* 1. Tasto Loop */}
                  <button
                    onClick={toggleLoop}
                    className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all cursor-pointer border ${isLooping
                        ? 'text-violet-600 dark:text-violet-400 bg-violet-500/10 border-violet-500/30 shadow-[0_0_12px_rgba(139,92,246,0.2)]'
                        : 'text-slate-400 hover:text-slate-600 dark:text-violet-400/40 dark:hover:text-violet-400/70 border-slate-200 dark:border-violet-500/10 bg-slate-50 dark:bg-slate-900/20'
                      }`}
                    title={isLooping ? "Disattiva Loop" : "Attiva Loop"}
                  >
                    <Repeat className={`w-4 h-4 ${isLooping ? 'stroke-[2.5px]' : ''}`} />
                  </button>

                  {/* 2. Simbolo Pulito Indietro -10s */}
                  <button onClick={skipBackward} className="p-2 text-slate-400 hover:text-violet-600 dark:text-violet-400/60 dark:hover:text-violet-300 transition-colors cursor-pointer">
                    <SkipBack className="w-5 h-5 fill-current" />
                  </button>

                  {/* 3. Pulsante Centrale Play/Pausa */}
                  <button onClick={toggleAudioPlayback} className="w-12 h-12 rounded-full bg-violet-600 text-white flex items-center justify-center shadow-[0_0_20px_rgba(139,92,246,0.3)] hover:bg-violet-700 hover:scale-105 transition-all duration-300 cursor-pointer flex-shrink-0">
                    {audioPlaying ? <Pause className="w-5 h-5 fill-current" /> : <Play className="w-5 h-5 fill-current ml-1" />}
                  </button>

                  {/* 4. Simbolo Pulito Avanti +10s */}
                  <button onClick={skipForward} className="p-2 text-slate-400 hover:text-violet-600 dark:text-violet-400/60 dark:hover:text-violet-300 transition-colors cursor-pointer">
                    <SkipForward className="w-5 h-5 fill-current" />
                  </button>

                  {/* 5. Tasto Cambia File (Risolto lo sfarfallio bianco su hover) */}
                  <label
                    htmlFor="audio-file-uploader"
                    className="w-9 h-9 rounded-xl flex items-center justify-center border text-slate-400 hover:text-slate-600 dark:text-violet-400/40 dark:hover:text-violet-400/70 border-slate-200 dark:border-violet-500/10 bg-slate-50 dark:bg-slate-900/20 hover:bg-slate-100 dark:hover:bg-slate-900/40 transition-colors duration-200 cursor-pointer shadow-none group"
                    title="Cambia traccia audio"
                  >
                    <Upload className="w-4 h-4 transition-colors group-hover:text-violet-600 dark:group-hover:text-violet-400" />
                  </label>
                </div>

              </div>
            )}
          </div>
        </BentoWidget>

      </main>
    </div>
  );
}