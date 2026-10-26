/**
 * @file frontend/src/app/control-plane/layout.tsx
 * @description Shell of the Control Plane: session gate and navigation (M11),
 * a reminder until the first-run setup is done (M12), in the Nucleo's style
 * (F2).
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import React, { useEffect, useState } from "react";

import AuthGate from "@/components/control-plane/AuthGate";
import styles from "@/components/control-plane/control.module.css";
import { getJson, postJson } from "@/lib/api/client";
import type { SettingsView } from "@/lib/api/settings";

const SECTIONS = [
    { href: "/control-plane/approvals", label: "APPROVAZIONI" },
    { href: "/control-plane/runs", label: "RUN" },
    { href: "/control-plane/memory", label: "MEMORIA" },
    { href: "/control-plane/security", label: "SICUREZZA" },
    { href: "/control-plane/voice", label: "VOCE" },
    { href: "/control-plane/settings", label: "IMPOSTAZIONI" },
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
        <div role="status" className={styles.banner}>
            Il primo avvio non è finito.{" "}
            <Link href="/control-plane/setup" className={styles.link}>
                Completalo
            </Link>{" "}
            per scegliere modelli, prezzi e budget.
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
        <div className={styles.shell}>
            <AuthGate>
                <header className={styles.top}>
                    <Link href="/" className={styles.mark}>
                        ÆHUB<small>CONTROL PLANE</small>
                    </Link>
                    <nav className={styles.nav} aria-label="Sezioni">
                        {SECTIONS.map((section) => (
                            <Link
                                key={section.href}
                                href={section.href}
                                aria-current={pathname?.startsWith(section.href) ? "page" : undefined}
                            >
                                {section.label}
                            </Link>
                        ))}
                    </nav>
                    <div className={styles.topEnd}>
                        <Link href="/" className={styles.quiet}>
                            ← Nucleo
                        </Link>
                        <button type="button" onClick={logout} className={styles.quiet}>
                            Esci
                        </button>
                    </div>
                </header>
                <SetupReminder pathname={pathname} />
                {children}
            </AuthGate>
        </div>
    );
}
