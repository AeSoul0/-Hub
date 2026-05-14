"use client"; // Marks this file as a Client Component in Next.js, allowing the use of React hooks like useState and useEffect

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
// The correct exported name is Youtube (Wait, actually Lucide often uses 'Youtube' or 'Video')
// Let's use the standard Lucide naming convention:
import { Cloud, Play, GraduationCap, Activity, LayoutDashboard } from "lucide-react"; interface WeatherData {
  city: string;
  temperature: string;
  condition: string;
}

export default function Home() {
  // State variables to store the data fetched from our Python backend
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [backendStatus, setBackendStatus] = useState("Connecting...");

  // useEffect runs once when the component is first rendered (mounted) on the screen
  useEffect(() => {
    // 1. Fetch the main backend status to check if Python server is up
    fetch("http://localhost:3002/")
      .then((res) => res.json())
      .then((data) => setBackendStatus(data.status))
      .catch(() => setBackendStatus("Offline")); // Fallback if the Python server is unreachable

    // 2. Fetch the mock Weather data from our specific API endpoint
    fetch("http://localhost:3002/api/weather")
      .then((res) => res.json())
      .then((data) => setWeather(data))
      .catch((err) => console.error("Weather fetch error:", err));
  }, []);

  return (
    // Main container with dark background (zinc-950) and custom typography
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6 font-[family-name:var(--font-geist-sans)]">

      {/* --- Header Area --- */}
      <header className="max-w-6xl mx-auto mb-10 flex justify-between items-center">

        {/* Logo and App Title */}
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold">Æ</div>
          <h1 className="text-2xl font-bold tracking-tight">ÆHub</h1>
        </div>

        {/* Backend connection status indicator */}
        <div className="flex items-center gap-2 text-sm">
          {/* The Activity icon dynamically changes color based on the server status */}
          <Activity className={`w-4 h-4 ${backendStatus === "Online" ? "text-emerald-500" : "text-red-500"}`} />
          <span className="text-zinc-400">System Status: {backendStatus}</span>
        </div>
      </header>

      {/* --- Main Bento Grid Layout --- 
          - grid-cols-1: 1 column on mobile screens
          - md:grid-cols-3: 3 columns on tablet screens
          - lg:grid-cols-4: 4 columns on large desktop screens
          - auto-rows-[180px]: forces each grid row to be exactly 180px high
      */}
      <main className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4 auto-rows-[180px]">

        {/* Weather Widget - Spans 2 columns on medium screens and up (md:col-span-2) */}
        <Card className="md:col-span-2 bg-zinc-900/50 border-zinc-800 backdrop-blur-sm overflow-hidden">
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-sm font-medium">Local Weather</CardTitle>
            <Cloud className="w-4 h-4 text-blue-400" />
          </CardHeader>
          <CardContent>
            {/* Conditional rendering: display data if available, otherwise show a pulsing loading state */}
            {weather ? (
              <div className="mt-2">
                <div className="text-4xl font-bold">{weather.temperature}</div>
                <p className="text-zinc-400">{weather.city} — {weather.condition}</p>
              </div>
            ) : (
              <p className="text-zinc-500 animate-pulse">Loading weather...</p>
            )}
          </CardContent>
        </Card>

        {/* Infostud Placeholder Widget (Standard 1x1 square) */}
        <Card className="bg-zinc-900/50 border-zinc-800 flex flex-col justify-between p-4 group cursor-pointer hover:border-purple-500/50 transition-all">
          <div className="flex justify-between items-start">
            <GraduationCap className="w-6 h-6 text-purple-400" />
          </div>
          <div>
            <div className="text-2xl font-bold">28.5</div>
            <p className="text-xs text-zinc-500 uppercase tracking-wider font-semibold">Average GPA</p>
          </div>
        </Card>

        {/* YouTube Downloader Placeholder Widget (Standard 1x1 square) */}
        <Card className="bg-zinc-900/50 border-zinc-800 flex flex-col justify-between p-4 group cursor-pointer hover:border-red-500/50 transition-all">
          <div className="flex justify-between items-start">
            <Play className="w-6 h-6 text-red-500" />          </div>
          <div>
            <div className="text-sm font-bold">Converter</div>
            <p className="text-xs text-zinc-500 uppercase tracking-wider font-semibold">YouTube to MP3</p>
          </div>
        </Card>

        {/* Empty Modular Space for future Agents/Widgets - Spans 2 columns on large screens */}
        <Card className="lg:col-span-2 bg-gradient-to-br from-zinc-900 to-zinc-800 border-zinc-800 flex items-center justify-center border-dashed border-2">
          <div className="text-center text-zinc-500">
            <LayoutDashboard className="w-8 h-8 mx-auto mb-2 opacity-20" />
            <p className="text-sm">More modules coming soon...</p>
          </div>
        </Card>

      </main>
    </div>
  );
}