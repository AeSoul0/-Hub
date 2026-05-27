"use client";

import { useEffect, useState } from "react";
import Header from "../components/Header";
import WeatherWidget from "../components/WeatherWidget";
import AcademicWidget from "../components/AcademicWidget";
import Yt_To_Mp3_Widget from "../components/Yt_To_Mp3_Widget";
import AudioPlayerWidget from "../components/AudioPlayerWidget";
import CoreOrchestratorWidget from "../components/CoreOrchestratorWidget";
import BentoWidget from "../components/BentoWidget";
import { LayoutDashboard } from "lucide-react";

export default function Home() {
  const [isDarkMode, setIsDarkMode] = useState(true);

  // Synchronizes the local React state with the Tailwind CSS root document class configuration on initial mount
  useEffect(() => {
    setIsDarkMode(document.documentElement.classList.contains('dark'));
  }, []);

  // Standard logical execution for DOM class toggling, removing previously failed batch rendering approaches
  const toggleTheme = () => {
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
  };

  return (
    <div className="min-h-screen text-slate-800 dark:text-cyan-50 p-6 font-[family-name:var(--font-geist-sans)] relative overflow-hidden z-0">

      {/* CRITICAL FIX: 
        Injects a global CSS rule binding the background transition directly to the underlying <body> element. 
        This acts as the absolute baseline, preventing any default white browser canvas from shining through 
        while the GPU calculates upper layer CSS backdrop-filters. 
      */}
      <style dangerouslySetInnerHTML={{
        __html: `
        body {
          background-color: #f8fafc; /* Equivalent to Tailwind slate-50 */
          transition: background-color 150ms ease-out;
        }
        html.dark body {
          background-color: #030508; /* Deep space abyssal void */
        }

        @keyframes agent-linked-pulse { 0%, 100% { opacity: 0.5; } 50% { opacity: 1; text-shadow: 0 0 12px rgba(6, 182, 212, 0.6); } }
        @keyframes wave-pulse { 0%, 100% { height: 4px; } 50% { height: 20px; } }
        
        .holographic-space { background-image: radial-gradient(circle at 50% 0%, rgba(15, 118, 110, 0.04) 0%, transparent 60%), radial-gradient(circle at 100% 100%, rgba(15, 118, 110, 0.03) 0%, transparent 50%); }
        html.dark .holographic-space { background-image: radial-gradient(circle at 50% 0%, rgba(6, 182, 212, 0.08) 0%, transparent 60%), radial-gradient(circle at 100% 100%, rgba(6, 182, 212, 0.05) 0%, transparent 50%); }
        
        .depth-mesh { background-size: 60px 60px; background-image: linear-gradient(rgba(15, 118, 110, 0.02) 1px, transparent 1px); transform: perspective(500px) rotateX(60deg); transform-origin: top center; }
        html.dark .depth-mesh { background-image: linear-gradient(rgba(6, 182, 212, 0.03) 1px, transparent 1px); transform: perspective(500px) rotateX(60deg); transform-origin: top center; }
        
        @keyframes newsTicker {
          0% { transform: translate3d(0, 0, 0); }
          100% { transform: translate3d(-50%, 0, 0); }
        }
        .animate-news-ticker {
          display: inline-block;
          white-space: nowrap;
          animation: newsTicker 12s linear infinite;
        }
        .animate-news-ticker:hover { animation-play-state: paused; }
      `}} />

      {/* Aesthetic environmental emitters utilizing global theme transitions */}
      <div className="fixed inset-0 holographic-space pointer-events-none -z-20 transition-all duration-150 ease-out" />
      <div className="fixed top-0 left-0 w-full h-[200vh] depth-mesh pointer-events-none -z-20 opacity-50 transition-all duration-150 ease-out" />

      {/* Renders global aesthetic orchestration context headers */}
      <Header isDarkMode={isDarkMode} toggleTheme={toggleTheme} />

      {/* Main layout composition structural view layer built out of custom micro-components */}
      <main className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 auto-rows-[240px] items-stretch relative z-10 transition-colors duration-150 ease-out">

        <WeatherWidget />
        <AcademicWidget />
        <Yt_To_Mp3_Widget />

        <BentoWidget variant="slot" title={<>Module<br />Alpha</>} icon={LayoutDashboard} colorKey="cyan" />

        <CoreOrchestratorWidget />
        <AudioPlayerWidget />

      </main>
    </div>
  );
}