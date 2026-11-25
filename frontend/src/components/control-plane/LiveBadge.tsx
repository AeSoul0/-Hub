/**
 * @file frontend/src/components/control-plane/LiveBadge.tsx
 * @description Shows whether the page receives live events.
 */
import React from "react";

import type { ConnectionState } from "@/lib/api/events";

import styles from "./control.module.css";

const LABELS: Record<ConnectionState, { text: string; tone: string }> = {
    connecting: { text: "connessione…", tone: "" },
    live: { text: "in linea", tone: "ok" },
    offline: { text: "offline, riconnessione", tone: "bad" },
};

export default function LiveBadge({ state }: { state: ConnectionState }) {
    const label = LABELS[state];

    return (
        <span className={styles.badge} data-tone={label.tone || undefined} role="status">
            {label.text}
        </span>
    );
}
