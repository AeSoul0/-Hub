// Architectural design tokens dictionary providing unified layout style bounds
export const THEME_COLORS = {
    cyan: {
        glow: "bg-cyan-400/20 dark:bg-cyan-400/20",
        accent: "text-cyan-600 dark:text-cyan-400",
        dot: "bg-cyan-500 dark:bg-cyan-400",
        shadow: "hover:shadow-[0_15px_30px_-10px_rgba(6,182,212,0.15)] dark:hover:shadow-[0_0_30px_-5px_rgba(6,182,212,0.25)]",
        // 10% opacity color foundations eliminate Chrome's color-mixing lag calculations on transition states
        borderBase: "border-cyan-400/10 dark:border-white/5",
        borderHover: "hover:border-cyan-400/60 dark:hover:border-cyan-400/40"
    },
    indigo: {
        glow: "bg-indigo-400/20 dark:bg-indigo-400/20",
        accent: "text-indigo-600 dark:text-indigo-400",
        dot: "bg-indigo-500 dark:bg-indigo-400",
        shadow: "hover:shadow-[0_15px_30px_-10px_rgba(99,102,241,0.15)] dark:hover:shadow-[0_0_30px_-5px_rgba(99,102,241,0.25)]",
        borderBase: "border-indigo-400/10 dark:border-white/5",
        borderHover: "hover:border-indigo-400/60 dark:hover:border-indigo-400/40"
    },
    rose: {
        glow: "bg-rose-400/20 dark:bg-rose-400/20",
        accent: "text-rose-600 dark:text-rose-400",
        dot: "bg-rose-500 dark:bg-rose-400",
        shadow: "hover:shadow-[0_15px_30px_-10px_rgba(244,63,94,0.15)] dark:hover:shadow-[0_0_30px_-5px_rgba(244,63,94,0.25)]",
        borderBase: "border-rose-400/10 dark:border-white/5",
        borderHover: "hover:border-rose-400/60 dark:hover:border-rose-400/40"
    }
};

export type ColorKey = keyof typeof THEME_COLORS;