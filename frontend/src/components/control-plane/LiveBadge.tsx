/**
 * @file frontend/src/components/control-plane/LiveBadge.tsx
 * @description Shows whether the page receives live events.
 */
import React from "react";

import type { ConnectionState } from "@/lib/api/events";

const LABELS: Record<ConnectionState, { text: string; className: string }> = {
    connecting: { text: "connecting", className: "bg-gray-700 text-gray-300" },
    live: { text: "live", className: "bg-green-800 text-green-200" },
    offline: { text: "offline, reconnecting", className: "bg-red-900 text-red-200" },
};

export default function LiveBadge({ state }: { state: ConnectionState }) {
    const label = LABELS[state];

    return (
        <span className={`text-xs font-mono px-2 py-0.5 rounded ${label.className}`} role="status">
            {label.text}
        </span>
    );
}
