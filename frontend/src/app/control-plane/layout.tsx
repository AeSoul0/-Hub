/**
 * @file frontend/src/app/control-plane/layout.tsx
 * @description Shell of the Control Plane: session gate and navigation (M11),
 * a reminder until the first-run setup is done (M12), in the Nucleo's style
 * (F2). Tools and skills since F5, the home since F7.
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import React, { useEffect, useState } from "react";

import AuthGate from "@/components/control-plane/AuthGate";
import styles from "@/components/control-plane/control.module.css";
import { getJson, postJson } from "@/lib/api/client";
import type { SettingsView } from "@/lib/api/settings";
import { catalog, useText } from "@/lib/i18n";

const PATHS = [
    "approvals",
    "runs",
    "memory",
    "documents",
    "home",
    "tools",
    "skills",
    "security",
    "voice",
    "settings",
    "system",
] as const;

type Section = (typeof PATHS)[number];

const TEXT = catalog({
    en: {
        sections: {
            approvals: "APPROVALS",
            runs: "RUNS",
            memory: "MEMORY",
            documents: "DOCUMENTS",
            home: "HOME",
            tools: "TOOLS",
            skills: "SKILLS",
            security: "SECURITY",
            voice: "VOICE",
            settings: "SETTINGS",
            system: "SYSTEM",
        } as Record<Section, string>,
        nav: "Sections",
        logout: "Log out",
        setupPending: "The first start is not finished.",
        setupLink: "Finish it",
        setupRest: "to choose models, prices and budget.",
    },
    it: {
        sections: {
            approvals: "APPROVAZIONI",
            runs: "RUN",
            memory: "MEMORIA",
            documents: "DOCUMENTI",
            home: "CASA",
            tools: "STRUMENTI",
            skills: "SKILL",
            security: "SICUREZZA",
            voice: "VOCE",
            settings: "IMPOSTAZIONI",
            system: "SISTEMA",
        } as Record<Section, string>,
        nav: "Sezioni",
        logout: "Esci",
        setupPending: "Il primo avvio non è finito.",
        setupLink: "Completalo",
        setupRest: "per scegliere modelli, prezzi e budget.",
    },
});

/**
 * Shown on every page but the setup itself while the first-run setup is not
 * finished. Checked again on each navigation.
 */
function SetupReminder({ pathname }: { pathname: string | null }) {
    const t = useText(TEXT);
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
            {t.setupPending}{" "}
            <Link href="/control-plane/setup" className={styles.link}>
                {t.setupLink}
            </Link>{" "}
            {t.setupRest}
        </div>
    );
}

export default function ControlPlaneLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const t = useText(TEXT);

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
                    <nav className={styles.nav} aria-label={t.nav}>
                        {PATHS.map((path) => (
                            <Link
                                key={path}
                                href={`/control-plane/${path}`}
                                aria-current={pathname?.startsWith(`/control-plane/${path}`) ? "page" : undefined}
                            >
                                {t.sections[path]}
                            </Link>
                        ))}
                    </nav>
                    <div className={styles.topEnd}>
                        <Link href="/" className={styles.quiet}>
                            ← Nucleo
                        </Link>
                        <button type="button" onClick={logout} className={styles.quiet}>
                            {t.logout}
                        </button>
                    </div>
                </header>
                <SetupReminder pathname={pathname} />
                {children}
            </AuthGate>
        </div>
    );
}
