/**
 * @file frontend/src/app/control-plane/layout.tsx
 * @description Shell of the Control Plane: session gate and navigation (M11).
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import React from "react";

import AuthGate from "@/components/control-plane/AuthGate";
import { postJson } from "@/lib/api/client";

const SECTIONS = [
    { href: "/control-plane/approvals", label: "Approvals" },
    { href: "/control-plane/runs", label: "Runs" },
    { href: "/control-plane/memory", label: "Memory" },
    { href: "/control-plane/security", label: "Security" },
] as const;

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
                {children}
            </AuthGate>
        </div>
    );
}
