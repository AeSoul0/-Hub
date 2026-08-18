/**
 * @file frontend/src/components/widgets/DynamicArtifactRenderer.tsx
 * @description Core module for A.U.R.O.R.A. System
 *
 * Implements primary logic and architectural constraints.
 *
 * Architectural constraints and responsibilities apply here.
 * Testability and dependency separation are enforced.
 */

"use client";

import React, { Suspense } from "react";
import dynamic from "next/dynamic";
import { Loader2 } from "lucide-react";

// Dynamically import widgets to avoid bloating the main bundle.
// This is Phase 11: Dynamic GUI Engine.
// A.U.R.O.R.A. will return a JSON artifact like: { "type": "weather", "data": {...} }
// and this component will render the correct React Component dynamically.

const WeatherWidget = dynamic(() => import("./WeatherWidget"), {
  loading: () => <WidgetLoader />,
});

const AcademicWidget = dynamic(() => import("./AcademicWidget"), {
  loading: () => <WidgetLoader />,
});

const BentoWidget = dynamic(() => import("./BentoWidget"), {
  loading: () => <WidgetLoader />,
});

const AudioPlayerWidget = dynamic(() => import("./AudioPlayerWidget"), {
  loading: () => <WidgetLoader />,
});

const YtToMp3Widget = dynamic(() => import("./Yt_To_Mp3_Widget"), {
  loading: () => <WidgetLoader />,
});

const CoreOrchestratorWidget = dynamic(() => import("./CoreOrchestratorWidget"), {
  loading: () => <WidgetLoader />,
});

export interface Artifact {
  id: string;
  type: string;
  data: any;
}

interface DynamicArtifactRendererProps {
  artifact: Artifact;
}

const WidgetLoader = () => (
  <div className="flex items-center justify-center h-48 w-full bg-slate-900/50 rounded-xl border border-slate-800">
    <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
  </div>
);

export function DynamicArtifactRenderer({ artifact }: DynamicArtifactRendererProps) {
  switch (artifact.type) {
    case "weather":
      return <WeatherWidget {...artifact.data} />;
    case "academic":
      return <AcademicWidget />; // Assuming it fetches its own data or accepts props
    case "audio_player":
      return <AudioPlayerWidget src={artifact.data.src} title={artifact.data.title} />;
    case "yt_mp3":
      return <YtToMp3Widget />;
    case "bento":
      return (
        <BentoWidget title="Bento Data" icon={Loader2} colorKey="indigo">
          <div className="p-4 text-sm text-slate-300">
            {JSON.stringify(artifact.data?.items)}
          </div>
        </BentoWidget>
      );
    case "orchestrator":
      return <CoreOrchestratorWidget />;
    default:
      return (
        <div className="p-4 bg-red-900/20 border border-red-800 rounded-xl text-red-400 font-mono text-sm">
          Unknown Artifact Type: {artifact.type}
        </div>
      );
  }
}
