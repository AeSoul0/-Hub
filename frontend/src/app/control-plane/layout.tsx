/**
 * @file frontend/src/app/control-plane/layout.tsx
 * @description Shell of the Control Plane: session gate and navigation (M11),
 * and a reminder until the first-run setup is done (M12).
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import React, { useEffect, useState } from "react";

import AuthGate from "@/components/control-plane/AuthGate";
import { getJson, postJson } from "@/lib/api/client";
import type { SettingsView } from "@/lib/api/settings";

const SECTIONS = [
    { href: "/control-plane/approvals", label: "Approvals" },
    { href: "/control-plane/runs", label: "Runs" },
    { href: "/control-plane/memory", label: "Memory" },
    { href: "/control-plane/security", label: "Security" },
    { href: "/control-plane/settings", label: "Settings" },
] as const;

/**
 * Shown on every page but the setup itself while the first-run setup is not
 * finished. Checked again on each navigation.
 */
function SetupReminder({ pathname }: { pathname: string | null }) {
    const [pending, setPending] = useState(false);

    useEffect(() => {
        let active = true;
        getJson<SettingsView>("/api/settings")
            .then((view) => active && setPending(!view.onboarding.completed))
            .catch(() => active && setPending(false));
        return () => {
            active = false;
        };
    }, [pathname]);

    if (!pending || pathname?.startsWith("/control-plane/setup")) {
        return null;
    }

    return (
        <div role="status" className="px-8 py-2 bg-cyan-950 text-cyan-100 text-sm border-b border-cyan-900">
            The first-run setup is not finished.{" "}
            <Link href="/control-plane/setup" className="underline">
                Finish it
            </Link>{" "}
            to choose models, prices and budget.
        </div>
    );
}

export default function ControlPlaneLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();

    const logout = async () => {
        try {
            await postJson("/api/auth/logout", {});
        } finally {
            window.location.reload();
        }
    };

    return (
        <div className="min-h-screen text-white" style={{ backgroundColor: "#111" }}>
            <AuthGate>
                <nav className="flex flex-wrap items-center gap-2 px-8 py-4 border-b border-gray-800">
                    <Link href="/" className="mr-4 font-mono text-cyan-500 font-bold">
                        ÆHub
                    </Link>
                    {SECTIONS.map((section) => {
                        const active = pathname?.startsWith(section.href);
                        return (
                            <Link
                                key={section.href}
                                href={section.href}
                                aria-current={active ? "page" : undefined}
                                className={`px-3 py-1 rounded ${
                                    active ? "bg-orange-600 text-white" : "text-gray-300 hover:bg-gray-800"
                                }`}
                            >
                                {section.label}
                            </Link>
                        );
                    })}
                    <button onClick={logout} className="ml-auto text-sm text-gray-400 hover:text-white">
                        Sign out
                    </button>
                </nav>
                <SetupReminder pathname={pathname} />
                {children}
            </AuthGate>
        </div>
    );
}
