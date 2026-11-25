/**
 * @file frontend/src/components/control-plane/LiveBadge.tsx
 * @description Shows whether the page receives live events.
 */
import React from "react";

import type { ConnectionState } from "@/lib/api/events";
import { catalog, useText } from "@/lib/i18n";

import styles from "./control.module.css";

const TONES: Record<ConnectionState, string> = { connecting: "", live: "ok", offline: "bad" };

const LABELS = catalog<Record<ConnectionState, string>>({
    en: { connecting: "connecting…", live: "online", offline: "offline, reconnecting" },
    it: { connecting: "connessione…", live: "in linea", offline: "offline, riconnessione" },
});

export default function LiveBadge({ state }: { state: ConnectionState }) {
    const labels = useText(LABELS);

    return (
        <span className={styles.badge} data-tone={TONES[state] || undefined} role="status">
            {labels[state]}
        </span>
    );
}
