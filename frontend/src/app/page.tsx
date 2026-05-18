"use client";

import { useEffect, useState } from "react";
import { Cloud, Play, GraduationCap, Activity, LayoutDashboard, Sun, Moon } from "lucide-react";

interface WeatherData {
  city: string;
  temperature: string;
  condition: string;
}

// ============================================================================
// 1. DESIGN SYSTEM: DESIGN DICTIONARY / THEME MAPPING
// ============================================================================
const THEME_COLORS = {
  cyan: {
    glow: "bg-cyan-200/50 group-hover:bg-cyan-300/60 dark:bg-cyan-500/10 dark:group-hover:bg-cyan-500/20",
    textHover: "group-hover:text-cyan-600 dark:group-hover:text-cyan-400",
    icon: "text-cyan-500 dark:text-cyan-400",
    dot: "bg-cyan-400",
    subText: "text-cyan-600 dark:text-cyan-400"
  },
  indigo: {
    glow: "bg-indigo-200/50 group-hover:bg-indigo-300/60 dark:bg-indigo-500/10 dark:group-hover:bg-indigo-500/20",
    textHover: "group-hover:text-indigo-600 dark:group-hover:text-indigo-400",
    icon: "text-indigo-500 dark:text-indigo-400",
    dot: "bg-indigo-400",
    subText: "text-indigo-600 dark:text-indigo-400"
  },
  rose: {
    glow: "bg-rose-200/50 group-hover:bg-rose-300/60 dark:bg-rose-500/10 dark:group-hover:bg-rose-500/20",
    textHover: "group-hover:text-rose-600 dark:group-hover:text-rose-400",
    icon: "text-rose-500 dark:text-rose-400",
    dot: "bg-rose-400",
    subText: "text-rose-600 dark:text-rose-400"
  }
};

type ColorKey = keyof typeof THEME_COLORS;

// ============================================================================
// 2. MODULAR COMPONENT: BENTO WIDGET
// ============================================================================
function BentoWidget({
  title,
  icon: Icon,
  mainText,
  subTextLeft,
  subTextRight,
  colorKey,
  colSpan = 1,
  textSize = "text-5xl",
  isLoading = false
}: {
  title: string;
  icon: any;
  mainText?: string;
  subTextLeft?: string;
  subTextRight?: string;
  colorKey: ColorKey;
  colSpan?: number;
  textSize?: string;
  isLoading?: boolean;
}) {
  const colors = THEME_COLORS[colorKey];
  const colClass = colSpan === 2 ? "md:col-span-2" : "";

  return (
    // FIX: Ultra-fast 150ms transitions for snappy, native-like responsiveness
    <div className={`relative flex flex-col justify-between p-6 rounded-3xl overflow-hidden group transition-all duration-150 ease-out hover:-translate-y-1 z-0 antialiased transform-gpu !bg-white border-white shadow-[0_10px_40px_-10px_rgba(0,0,0,0.08)] hover:shadow-[0_20px_50px_-10px_rgba(0,0,0,0.15)] dark:!bg-[#0A101A]/60 dark:border-cyan-500/10 dark:backdrop-blur-xl dark:shadow-none dark:hover:border-cyan-500/30 ${colClass}`}>

      {/* Radial Environmental Glow Mapping */}
      <div className={`absolute top-0 right-0 w-32 h-32 rounded-full blur-3xl transition-all duration-150 ease-out -z-10 opacity-0 group-hover:opacity-100 ${colors.glow}`} />

      {/* Widget Header Interface */}
      <div className="flex justify-between items-start">
        {/* Zero-latency snap for dark mode text, fast 150ms fade for light mode */}
        <span className={`text-[11px] font-mono uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500 transition-colors duration-150 dark:duration-0 ease-out ${colors.textHover}`}>
          {title}
        </span>
        <Icon className={`w-6 h-6 opacity-80 transition-colors duration-150 dark:duration-0 ease-out ${colors.icon}`} />
      </div>

      {/* Widget Metrics Layer */}
      <div>
        {isLoading ? (
          <p className="text-slate-400 dark:text-slate-500 font-mono text-sm animate-pulse uppercase tracking-widest mt-4">Syncing...</p>
        ) : (
          <>
            <div className={`${textSize} font-light tracking-tighter text-slate-800 dark:text-white mb-2 drop-shadow-sm dark:drop-shadow-none transition-colors duration-150`}>
              {mainText}
            </div>
            <div className="flex items-center gap-3">
              {subTextLeft && (
                <span className="text-sm font-medium text-slate-600 dark:text-slate-300 transition-colors duration-150">{subTextLeft}</span>
              )}
              {subTextLeft && subTextRight && (
                <span className={`w-1 h-1 rounded-full ${colors.dot}`}></span>
              )}
              {subTextRight && (
                <span className={`text-sm font-mono uppercase tracking-wider transition-colors duration-150 ${colors.subText}`}>{subTextRight}</span>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// 3. MAIN DASHBOARD HOME CONTEXT
// ============================================================================
export default function Home() {
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [backendStatus, setBackendStatus] = useState("Connecting...");
  const [isDarkMode, setIsDarkMode] = useState(true);

  useEffect(() => {
    fetch("http://127.0.0.1:3002/")
      .then((res) => res.json())
      .then((data) => setBackendStatus(data.status))
      .catch(() => setBackendStatus("Offline"));

    fetch("http://127.0.0.1:3002/api/weather")
      .then((res) => res.json())
      .then((data) => setWeather(data))
      .catch((err) => console.error("Weather fetch error:", err));
  }, []);

  return (
    <div className={isDarkMode ? "dark" : ""}>
      {/* Root Layout Canvas Frame - Accelerated to 150ms for near-instant theme toggling */}
      <div className="min-h-screen bg-slate-50 dark:bg-[#030508] text-slate-800 dark:text-cyan-50 p-6 font-[family-name:var(--font-geist-sans)] transition-colors duration-150 ease-out relative overflow-hidden z-0">

        {/* Soft Background Emitters */}
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-blue-200/40 dark:bg-cyan-500/10 blur-[120px] rounded-full pointer-events-none transition-all duration-150 ease-out -z-20" />
        <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-indigo-200/40 dark:bg-indigo-500/10 blur-[100px] rounded-full pointer-events-none transition-all duration-150 ease-out -z-20" />

        <header className="max-w-6xl mx-auto mb-12 flex justify-between items-center relative z-10">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-white dark:bg-cyan-950/30 border border-slate-200 dark:border-cyan-500/20 backdrop-blur-xl rounded-2xl flex items-center justify-center font-mono font-bold text-cyan-600 dark:text-cyan-400 shadow-md transition-all duration-150 ease-out">
              Æ
            </div>
            <h1 className="text-3xl font-light tracking-widest text-slate-800 dark:text-cyan-50 uppercase transition-colors duration-150 ease-out">
              Æ<span className="font-bold text-cyan-500 dark:text-cyan-400">Hub</span>
            </h1>
          </div>

          <div className="flex items-center gap-4">
            {/* System Status */}
            <div className="flex items-center gap-2 text-[11px] font-mono tracking-widest uppercase bg-white dark:bg-cyan-950/20 backdrop-blur-md px-4 py-2 rounded-full border border-slate-200 dark:border-cyan-500/20 shadow-sm transition-all duration-150 ease-out">
              <Activity className={`w-3.5 h-3.5 ${backendStatus === "Online" ? "text-cyan-500 dark:text-cyan-400 animate-pulse" : "text-red-500"}`} />
              <span className={backendStatus === "Online" ? "text-slate-600 dark:text-cyan-200" : "text-red-500 dark:text-red-400"}>
                SYS: {backendStatus}
              </span>
            </div>

            {/* THEME TOGGLE BUTTON - Perfectly synced, 150ms instant feeling */}
            <button
              onClick={() => setIsDarkMode(!isDarkMode)}
              className="w-10 h-10 flex items-center justify-center bg-white dark:bg-cyan-950/20 backdrop-blur-md border border-slate-200 dark:border-cyan-500/20 rounded-full hover:scale-110 hover:shadow-md transition-all duration-150 ease-out shadow-sm cursor-pointer relative transform-gpu"
            >
              <Sun className={`absolute w-4 h-4 text-slate-600 transition-all duration-150 ease-out transform-gpu ${isDarkMode ? 'opacity-0 scale-50 rotate-90' : 'opacity-100 scale-100 rotate-0'}`} />
              <Moon className={`absolute w-4 h-4 text-cyan-400 transition-all duration-150 ease-out transform-gpu ${isDarkMode ? 'opacity-100 scale-100 rotate-0' : 'opacity-0 scale-50 -rotate-90'}`} />
            </button>
          </div>
        </header>

        <main className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-8 auto-rows-[200px] relative z-10">
          <BentoWidget
            title="Local_Atmosphere"
            icon={Cloud}
            colorKey="cyan"
            colSpan={2}
            textSize="text-7xl"
            isLoading={!weather}
            mainText={weather?.temperature}
            subTextLeft={weather?.city}
            subTextRight={weather?.condition}
          />
          <BentoWidget
            title="Academic"
            icon={GraduationCap}
            colorKey="indigo"
            mainText="28.5"
            subTextRight="Average GPA"
          />
          <BentoWidget
            title="Media_Sync"
            icon={Play}
            colorKey="rose"
            textSize="text-3xl"
            mainText="Extractor"
            subTextRight="YT to MP3"
          />
          {/* Expansion Slot - Fixed to duration-150 for snappy hover and hardware accelerated */}
          <div className="lg:col-span-2 relative flex flex-col items-center justify-center p-6 rounded-3xl border-2 border-dashed transition-all duration-150 ease-out group cursor-pointer !bg-white border-slate-300 hover:!bg-slate-50 hover:border-slate-400 dark:!bg-[#05080F]/40 dark:border-cyan-500/20 dark:hover:!bg-[#0A101A]/60 dark:hover:border-cyan-500/40 transform-gpu antialiased">
            <LayoutDashboard className="w-8 h-8 mx-auto mb-4 text-slate-400 dark:text-cyan-900 group-hover:text-slate-500 dark:group-hover:text-cyan-600 transition-colors duration-150" />
            <p className="text-xs font-mono uppercase tracking-[0.2em] text-slate-400 dark:text-cyan-800 group-hover:text-slate-500 dark:group-hover:text-cyan-500 transition-colors duration-150">
              Ready for modules
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}