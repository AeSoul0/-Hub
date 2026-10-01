/**
 * @file frontend/src/components/widgets/DynamicArtifactRenderer.tsx
 * @description Implements DynamicArtifactRenderer.tsx.
 *
 * This module manages the frontend logic for DynamicArtifactRenderer.
 * Core interfaces: Artifact, DynamicArtifactRendererProps.
 */
"use client";

import React from "react";
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

const CoreOrchestratorWidget = dynamic(
  () => import("./CoreOrchestratorWidget"),
  {
    loading: () => <WidgetLoader />,
  }
);

export interface Artifact {
  id: string;
  type: string;
  data: Record<string, unknown>;
}

interface DynamicArtifactRendererProps {
  artifact: Artifact;
}

const WidgetLoader = () => (
  <div className="flex items-center justify-center h-48 w-full bg-slate-900/50 rounded-xl border border-slate-800">
    <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
  </div>
);

export function DynamicArtifactRenderer({
  artifact,
}: DynamicArtifactRendererProps) {
  switch (artifact.type) {
    case "weather":
      return <WeatherWidget {...artifact.data} />;

    case "academic":
      return <AcademicWidget />;

    case "audio_player": {
      // artifact.data is Record<string, unknown>, so narrow the values
      // before passing them to AudioPlayerWidget.
      const src =
        typeof artifact.data.src === "string"
          ? artifact.data.src
          : undefined;

      const title =
        typeof artifact.data.title === "string"
          ? artifact.data.title
          : undefined;

      return <AudioPlayerWidget src={src} title={title} />;
    }

    case "yt_mp3":
      return <YtToMp3Widget />;

    case "bento":
      return (
        <BentoWidget
          title="Bento Data"
          icon={Loader2}
          colorKey="indigo"
        >
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

