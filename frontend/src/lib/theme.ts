export type ColorKey = 'cyan' | 'indigo' | 'rose' | 'emerald' | 'amber' | 'violet';

export const THEME_COLORS: Record<ColorKey, {
    borderBase: string;
    borderHover: string;
    shadow: string;
    glow: string;
    accent: string;
    dot: string;
}> = {
    cyan: {
        borderBase: "border-cyan-500/30 dark:border-white/[0.08]",
        borderHover: "hover:border-cyan-500 dark:hover:border-cyan-400/60", // Opacità aumentata a 0.6
        shadow: "hover:shadow-[0_8px_30px_rgb(6,182,212,0.12)] dark:hover:shadow-[0_0_30px_-5px_rgba(6,182,212,0.15)]",
        glow: "bg-cyan-400/20 dark:bg-cyan-500/15",
        accent: "text-cyan-600 dark:text-cyan-400",
        dot: "bg-cyan-500 dark:bg-cyan-400"
    },
    indigo: {
        borderBase: "border-indigo-500/30 dark:border-white/[0.08]",
        borderHover: "hover:border-indigo-500 dark:hover:border-indigo-400/60",
        shadow: "hover:shadow-[0_8px_30px_rgb(99,102,241,0.12)] dark:hover:shadow-[0_0_30px_-5px_rgba(99,102,241,0.15)]",
        glow: "bg-indigo-400/20 dark:bg-indigo-500/15",
        accent: "text-indigo-600 dark:text-indigo-400",
        dot: "bg-indigo-500 dark:bg-indigo-400"
    },
    rose: {
        borderBase: "border-rose-500/30 dark:border-white/[0.08]",
        borderHover: "hover:border-rose-500 dark:hover:border-rose-400/60",
        shadow: "hover:shadow-[0_8px_30px_rgb(244,63,94,0.12)] dark:hover:shadow-[0_0_30px_-5px_rgba(244,63,94,0.15)]",
        glow: "bg-rose-400/20 dark:bg-rose-500/15",
        accent: "text-rose-600 dark:text-rose-400",
        dot: "bg-rose-500 dark:bg-rose-400"
    },
    violet: {
        borderBase: "border-violet-500/30 dark:border-white/[0.08]",
        borderHover: "hover:border-violet-500 dark:hover:border-violet-400/60",
        shadow: "hover:shadow-[0_8px_30px_rgb(139,92,246,0.12)] dark:hover:shadow-[0_0_30px_-5px_rgba(139,92,246,0.15)]",
        glow: "bg-violet-400/20 dark:bg-violet-500/15",
        accent: "text-violet-600 dark:text-violet-400",
        dot: "bg-violet-500 dark:bg-violet-400"
    },
    emerald: {
        borderBase: "border-emerald-500/30 dark:border-white/[0.08]",
        borderHover: "hover:border-emerald-500 dark:hover:border-emerald-400/60",
        shadow: "hover:shadow-[0_8px_30px_rgb(16,185,129,0.12)] dark:hover:shadow-[0_0_30px_-5px_rgba(16,185,129,0.15)]",
        glow: "bg-emerald-400/20 dark:bg-emerald-500/15",
        accent: "text-emerald-600 dark:text-emerald-400",
        dot: "bg-emerald-500 dark:bg-emerald-400"
    },
    amber: {
        borderBase: "border-amber-500/30 dark:border-white/[0.08]",
        borderHover: "hover:border-amber-500 dark:hover:border-amber-400/60",
        shadow: "hover:shadow-[0_8px_30px_rgb(245,158,11,0.12)] dark:hover:shadow-[0_0_30px_-5px_rgba(245,158,11,0.15)]",
        glow: "bg-amber-400/20 dark:bg-amber-500/15",
        accent: "text-amber-600 dark:text-amber-400",
        dot: "bg-amber-500 dark:bg-amber-400"
    }
};