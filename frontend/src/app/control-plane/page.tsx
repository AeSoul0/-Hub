/**
 * @file frontend/src/app/control-plane/page.tsx
 * @description The Control Plane opens on the first-run setup until it is
 * done (M12), then on the approval queue.
 */
"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import styles from "@/components/control-plane/control.module.css";
import { getJson } from "@/lib/api/client";
import type { SettingsView } from "@/lib/api/settings";

export default function ControlPlaneIndex() {
    const router = useRouter();

    useEffect(() => {
        getJson<SettingsView>("/api/settings")
            .then((view) =>
                router.replace(view.onboarding.completed ? "/control-plane/approvals" : "/control-plane/setup"),
            )
            .catch(() => router.replace("/control-plane/approvals"));
    }, [router]);

    return (
        <div className={styles.page}>
            <p className={styles.muted}>Caricamento…</p>
        </div>
    );
}
