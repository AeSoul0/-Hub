export type ColorKey = 'cyan' | 'indigo' | 'rose' | 'emerald' | 'amber' | 'violet';

// Core theme definitions establishing borders, shadows, and accent properties
export const THEME_COLORS: Record<ColorKey, {
    borderBase: string;
    borderHover: string;
    shadow: string;
    glow: string;
    accent: string;
    dot: string;
}> = {
    cyan: {
        borderBase: "border-white/[0.08]",
        borderHover: "hover:border-cyan-400/60",
        shadow: "hover:shadow-[0_0_30px_-5px_rgba(6,182,212,0.15)]",
        glow: "bg-cyan-500/15",
        accent: "text-cyan-400",
        dot: "bg-cyan-400"
    },
    indigo: {
        borderBase: "border-white/[0.08]",
        borderHover: "hover:border-indigo-400/60",
        shadow: "hover:shadow-[0_0_30px_-5px_rgba(99,102,241,0.15)]",
        glow: "bg-indigo-500/15",
        accent: "text-indigo-400",
        dot: "bg-indigo-400"
    },
    rose: {
        borderBase: "border-white/[0.08]",
        borderHover: "hover:border-rose-400/60",
        shadow: "hover:shadow-[0_0_30px_-5px_rgba(244,63,94,0.15)]",
        glow: "bg-rose-500/15",
        accent: "text-rose-400",
        dot: "bg-rose-400"
    },
    violet: {
        borderBase: "border-white/[0.08]",
        borderHover: "hover:border-violet-400/60",
        shadow: "hover:shadow-[0_0_30px_-5px_rgba(139,92,246,0.15)]",
        glow: "bg-violet-500/15",
        accent: "text-violet-400",
        dot: "bg-violet-400"
    },
    emerald: {
        borderBase: "border-white/[0.08]",
        borderHover: "hover:border-emerald-400/60",
        shadow: "hover:shadow-[0_0_30px_-5px_rgba(16,185,129,0.15)]",
        glow: "bg-emerald-500/15",
        accent: "text-emerald-400",
        dot: "bg-emerald-400"
    },
    amber: {
        borderBase: "border-white/[0.08]",
        borderHover: "hover:border-amber-400/60",
        shadow: "hover:shadow-[0_0_30px_-5px_rgba(245,158,11,0.15)]",
        glow: "bg-amber-500/15",
        accent: "text-amber-400",
        dot: "bg-amber-400"
    }
};