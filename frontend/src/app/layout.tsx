/**
 * @file frontend/src/app/layout.tsx
 * @description Implements layout.tsx.
 * 
 * This module manages the frontend logic for RootLayout.
 * Core interfaces: data structures.
 */
import type { Metadata } from "next";
// Fonts are bundled from npm (no request to Google at build or run time):
// the build works offline and the browser loads nothing from third parties.
import "@fontsource-variable/nunito";
import "@fontsource-variable/quicksand";
import "./style/globals.css";

// Define application metadata for SEO and browser tab display
export const metadata: Metadata = {
    title: "ÆHub",
    description: "Core Orchestrator Interface",
};

// Root layout component that wraps all application pages
export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    // Dynamic hydration wrapper configuring root font variable injections and establishing global theme
    return (
        <html
            lang="en"
            suppressHydrationWarning
            className="h-full antialiased dark"
        >
            {/* Root compositional layer establishing absolute background nodes with hardware-accelerated 150ms transitions */}
            <body className="min-h-full flex flex-col bg-[#030508] transition-colors duration-150 ease-out text-cyan-50 font-[family-name:var(--font-nunito)]">
                {children}
            </body>
        </html>
    );
}

