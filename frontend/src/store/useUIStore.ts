/**
 * @file frontend/src/store/useUIStore.ts
 * @description UI state management store using Zustand.
 *
 * Implements core logic and architectural definitions.
 */

import { create } from "zustand";
import { Artifact } from "@/components/widgets/DynamicArtifactRenderer";

// Defines the structure of an active draggable artifact window
export interface ArtifactWindow {
    id: string;
    artifact: Artifact;
    x: number;
    y: number;
    width: number;
    height: number;
    zIndex: number;
    isOpen: boolean;
}

interface UIStore {
    windows: ArtifactWindow[];
    spawnArtifact: (artifact: Artifact) => void;
    closeArtifact: (id: string) => void;
    updateWindow: (id: string, updates: Partial<ArtifactWindow>) => void;
    bringToFront: (id: string) => void;
}

export const useUIStore = create<UIStore>((set) => ({
    windows: [],
    spawnArtifact: (artifact) => set((state) => {
        // Find if we already have a window for this artifact type (to avoid duplicates of singletons like weather/academic)
        const exists = state.windows.find(w => w.artifact.type === artifact.type);
        if (exists) {
            // Just update data and bring to front
            return {
                windows: state.windows.map(w => w.id === exists.id ? { ...w, artifact, isOpen: true, zIndex: Date.now() } : w)
            };
        }
        
        // Spawn a new window
        const newWindow: ArtifactWindow = {
            id: Math.random().toString(36).substring(2, 9),
            artifact,
            x: 50 + state.windows.length * 40,
            y: 50 + state.windows.length * 40,
            width: 450,
            height: 380,
            zIndex: Date.now(),
            isOpen: true
        };
        return { windows: [...state.windows, newWindow] };
    }),
    
    // Closes and removes an artifact window by its ID
    closeArtifact: (id) => set((state) => ({
        windows: state.windows.filter((w) => w.id !== id),
    })),
    
    // Updates specific properties of an existing artifact window
    updateWindow: (id, updates) => set((state) => ({
        windows: state.windows.map((w) => (w.id === id ? { ...w, ...updates } : w)),
    })),
    
    // Raises a window to the front by updating its z-index
    bringToFront: (id) => set((state) => ({
        windows: state.windows.map((w) => (w.id === id ? { ...w, zIndex: Date.now() } : w)),
    })),
}));
