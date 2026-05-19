import React from 'react';
import { THEME_COLORS, ColorKey } from '../lib/theme';

interface BentoWidgetProps {
    variant?: "default" | "slot";
    title: string | React.ReactNode;
    icon: React.ComponentType<{ className?: string }>;
    mainText?: string;
    subTextLeft?: string;
    subTextRight?: string;
    colorKey: ColorKey;
    colSpan?: number;
    textSize?: string;
    isLoading?: boolean;
    children?: React.ReactNode;
}

export default function BentoWidget({
    variant = "default",
    title,
    icon: Icon,
    mainText,
    subTextLeft,
    subTextRight,
    colorKey,
    colSpan = 1,
    textSize = "text-5xl",
    isLoading = false,
    children
}: BentoWidgetProps) {
    const colors = THEME_COLORS[colorKey];
    const colClass = colSpan === 2 ? "md:col-span-2" : "";

    // Aggiunto hover:duration-75: animazione d'ingresso istantanea, uscita morbida a 300ms
    const baseClasses = `relative overflow-hidden group transition-all duration-300 hover:duration-75 ease-out hover:-translate-y-2 z-0 antialiased transform-gpu will-change-transform rounded-[2rem] p-6 flex flex-col ${colClass} ${colors.shadow}`;

    // Solid layout background mappings override backdrop configurations inside Light Mode environments to fix render issues
    const sharedBg = "bg-white dark:bg-[#0A101A]/60 dark:backdrop-blur-2xl shadow-[0_8px_30px_-10px_rgba(0,0,0,0.04)] dark:shadow-none";

    // Modificati i bordi per allinearsi alle nuove fondamenta cromatiche in modo dinamico
    const borderClasses = variant === "default"
        ? `border ${colors.borderBase} ${colors.borderHover}`
        : `border-2 border-dashed ${colors.borderBase} ${colors.borderHover}`;

    const layoutClasses = variant === "default"
        ? "justify-between"
        : "items-center justify-center text-center cursor-pointer";

    if (variant === "slot") {
        return (
            <div className={`${baseClasses} ${sharedBg} ${borderClasses} ${layoutClasses}`}>
                <div className="pointer-events-none absolute -top-6 -right-6 w-32 h-32 rounded-full blur-2xl transition-opacity duration-300 group-hover:duration-75 ease-out -z-10 opacity-0 group-hover:opacity-100 var(--colors-glow)" style={{ backgroundColor: 'transparent', backgroundImage: 'radial-gradient(circle, ' + colors.glow.split(' ')[0] + ' 0%, transparent 70%)' }} />
                <Icon className={`w-6 h-6 mb-4 transition-opacity duration-300 group-hover:duration-75 ease-out opacity-60 group-hover:opacity-100 ${colors.accent}`} />
                <p className={`text-[10px] font-bold uppercase tracking-[0.2em] transition-opacity duration-300 group-hover:duration-75 ease-out opacity-60 group-hover:opacity-100 ${colors.accent}`}>
                    {title}
                </p>
            </div>
        );
    }

    return (
        <div className={`${baseClasses} ${sharedBg} ${borderClasses} ${layoutClasses}`}>
            <div className={`pointer-events-none absolute -top-6 -right-6 w-32 h-32 rounded-full blur-2xl transition-opacity duration-300 group-hover:duration-75 ease-out -z-10 opacity-0 group-hover:opacity-100 ${colors.glow}`} />

            <div className="flex justify-between items-start">
                <span className={`text-[12px] font-bold uppercase tracking-[0.15em] transition-opacity duration-300 group-hover:duration-75 ease-out opacity-60 group-hover:opacity-100 ${colors.accent}`}>
                    {title}
                </span>
                <Icon className={`w-6 h-6 transition-opacity duration-300 group-hover:duration-75 ease-out opacity-60 group-hover:opacity-100 ${colors.accent}`} />
            </div>

            <div className="mt-auto">
                {isLoading ? (
                    <p className={`font-bold text-xs animate-pulse uppercase tracking-widest mt-4 opacity-60 ${colors.accent}`}>Syncing...</p>
                ) : (
                    <>
                        {mainText && (
                            <div className={`${textSize} font-[family-name:var(--font-quicksand)] font-semibold tracking-tight text-slate-900 dark:text-white mb-1 transition-colors duration-300 group-hover:duration-75 ease-out`}>
                                {mainText}
                            </div>
                        )}
                        {(subTextLeft || subTextRight) && (
                            <div className="flex items-center gap-2.5">
                                {subTextLeft && (
                                    <span className="text-sm font-semibold text-slate-500 dark:text-slate-300 transition-colors duration-300 ease-out">{subTextLeft}</span>
                                )}
                                {subTextLeft && subTextRight && (
                                    <span className={`w-1.5 h-1.5 rounded-full opacity-50 group-hover:opacity-100 transition-opacity duration-300 group-hover:duration-75 ease-out ${colors.dot}`}></span>
                                )}
                                {subTextRight && (
                                    <span className={`text-[11px] font-bold uppercase tracking-wider transition-opacity duration-300 group-hover:duration-75 ease-out opacity-60 group-hover:opacity-100 ${colors.accent}`}>{subTextRight}</span>
                                )}
                            </div>
                        )}
                        {children && <div className="w-full relative z-10">{children}</div>}
                    </>
                )}
            </div>
        </div>
    );
}