/**
 * @file frontend/src/components/layout/WorkspaceDesktop.tsx
 * @description Core module for A.U.R.O.R.A. System
 *
 * Implements primary logic and architectural constraints.
 * Architectural constraints and responsibilities apply here.
 * Testability and dependency separation are enforced.
 */

"use client";

import React from "react";
import { Rnd } from "react-rnd";
import { X, Maximize2 } from "lucide-react";
import { useUIStore } from "@/store/useUIStore";
import { DynamicArtifactRenderer } from "@/components/widgets/DynamicArtifactRenderer";

export default function WorkspaceDesktop() {
    const { windows, closeArtifact, updateWindow, bringToFront } = useUIStore();

    return (
        <div className="absolute inset-0 pointer-events-none z-50 overflow-hidden">
            {windows.map((win) => {
                if (!win.isOpen) return null;

                return (
                    <Rnd
                        key={win.id}
                        size={{ width: win.width, height: win.height }}
                        position={{ x: win.x, y: win.y }}
                        onDragStart={() => bringToFront(win.id)}
                        onDragStop={(e, d) => {
                            updateWindow(win.id, { x: d.x, y: d.y });
                        }}
                        onResizeStart={() => bringToFront(win.id)}
                        onResizeStop={(e, direction, ref, delta, position) => {
                            updateWindow(win.id, {
                                width: parseInt(ref.style.width, 10),
                                height: parseInt(ref.style.height, 10),
                                ...position,
                            });
                        }}
                        minWidth={300}
                        minHeight={200}
                        bounds="window"
                        dragHandleClassName="drag-handle"
                        className="pointer-events-auto flex flex-col bg-[#040914]/95 backdrop-blur-xl border border-cyan-900/50 shadow-2xl rounded-2xl overflow-hidden group"
                        style={{ zIndex: win.zIndex }}
                    >
                        {/* WIDGET TITLE BAR */}
                        <div className="drag-handle h-8 w-full bg-slate-900/80 border-b border-cyan-900/30 flex items-center justify-between px-3 cursor-move shrink-0">
                            <div className="flex items-center gap-2">
                                <div className="w-2 h-2 rounded-full bg-cyan-500/50 group-hover:bg-cyan-400 transition-colors" />
                                <span className="text-[10px] font-mono text-cyan-500/70 uppercase tracking-widest">
                                    SYS.{win.artifact.type}
                                </span>
                            </div>
                            
                            <div className="flex items-center gap-2 opacity-50 hover:opacity-100 transition-opacity">
                                <button className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white transition-colors">
                                    <Maximize2 className="w-3 h-3" />
                                </button>
                                <button 
                                    onClick={(e) => { e.stopPropagation(); closeArtifact(win.id); }}
                                    className="p-1 hover:bg-red-900/50 rounded text-slate-400 hover:text-red-400 transition-colors"
                                >
                                    <X className="w-3 h-3" />
                                </button>
                            </div>
                        </div>

                        {/* WIDGET CONTENT AREA */}
                        <div className="flex-1 overflow-hidden relative">
                            <DynamicArtifactRenderer artifact={win.artifact} />
                        </div>
                    </Rnd>
                );
            })}
        </div>
    );
}
