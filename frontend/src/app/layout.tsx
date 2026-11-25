/**
 * @file frontend/src/app/layout.tsx
 * @description Root layout: fonts, the space theme, the star field
 * behind every page and the interface language (lib/i18n).
 */
import type { Metadata } from "next";
// Fonts are bundled from npm (no request to Google at build or run time):
// the build works offline and the browser loads nothing from third parties.
import "@fontsource-variable/oxanium";
import "@fontsource-variable/ibm-plex-sans";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./style/globals.css";

import StarField from "@/components/nucleo/StarField";
import InterfaceProvider from "@/components/interface/InterfaceProvider";

export const metadata: Metadata = {
    title: "ÆHub",
    description: "ÆHub, the personal agent.",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en" className="h-full antialiased">
            <body className="min-h-full flex flex-col">
                <StarField />
                <div className="relative z-10 flex flex-1 flex-col">{children}</div>
                <InterfaceProvider />
            </body>
        </html>
    );
}
