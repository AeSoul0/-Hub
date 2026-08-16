"use client";

import { useState } from "react";
import { Menu, ChevronLeft, History, Settings, FolderOpen, Network } from "lucide-react";

export default function Sidebar() {
    const [isOpen, setIsOpen] = useState(false);

    return (
        <>
            {/* Mobile Toggle Button */}
            <button 
                onClick={() => setIsOpen(!isOpen)}
                className="fixed top-20 left-4 z-50 p-2 bg-[#040914] border border-cyan-900/50 rounded-lg text-cyan-500 hover:text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.1)] lg:hidden"
            >
                <Menu className="w-5 h-5" />
            </button>

            {/* Sidebar Overlay (Mobile) */}
            {isOpen && (
                <div 
                    className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 lg:hidden"
                    onClick={() => setIsOpen(false)}
                />
            )}

            {/* Sidebar Container */}
            <aside 
                className={`
                    fixed lg:sticky top-0 left-0 h-screen z-40
                    w-64 bg-[#040914]/95 backdrop-blur-xl border-r border-cyan-900/30
                    transition-transform duration-300 ease-in-out
                    flex flex-col
                    ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
                `}
            >
                {/* Header */}
                <div className="h-20 flex items-center justify-between px-6 border-b border-cyan-900/30">
                    <div className="font-mono text-cyan-500 font-bold tracking-widest text-sm flex items-center gap-2">
                        <Network className="w-4 h-4" />
                        <span>AE_HUB</span>
                    </div>
                    <button 
                        onClick={() => setIsOpen(false)}
                        className="lg:hidden text-cyan-700 hover:text-cyan-400"
                    >
                        <ChevronLeft className="w-5 h-5" />
                    </button>
                </div>

                {/* Modules Navigation */}
                <div className="flex-1 overflow-y-auto py-6 px-4 space-y-8">
                    
                    {/* Primary Modules */}
                    <div>
                        <h3 className="text-[10px] font-mono text-cyan-700 font-bold tracking-widest mb-3 px-2">MODULES</h3>
                        <ul className="space-y-1">
                            <li>
                                <a href="#" className="flex items-center gap-3 px-2 py-2 text-sm text-cyan-100 bg-cyan-900/20 rounded-lg border border-cyan-800/50">
                                    <FolderOpen className="w-4 h-4 text-cyan-400" />
                                    <span>Command Center</span>
                                </a>
                            </li>
                        </ul>
                    </div>

                    {/* Session History */}
                    <div>
                        <h3 className="text-[10px] font-mono text-cyan-700 font-bold tracking-widest mb-3 px-2">HISTORY</h3>
                        <ul className="space-y-1">
                            <li>
                                <button className="w-full flex items-center gap-3 px-2 py-2 text-sm text-cyan-400/60 hover:text-cyan-200 hover:bg-cyan-900/10 rounded-lg transition-colors">
                                    <History className="w-4 h-4" />
                                    <span className="truncate">Session Active</span>
                                </button>
                            </li>
                            {/* We can map over historical sessions here in the future */}
                        </ul>
                    </div>
                </div>

                {/* Footer Settings */}
                <div className="p-4 border-t border-cyan-900/30">
                    <button className="w-full flex items-center gap-3 px-2 py-2 text-sm text-cyan-500/60 hover:text-cyan-300 transition-colors">
                        <Settings className="w-4 h-4" />
                        <span>Core Settings</span>
                    </button>
                </div>
            </aside>
        </>
    );
}
