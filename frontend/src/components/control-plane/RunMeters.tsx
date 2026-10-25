/**
 * @file frontend/src/components/control-plane/RunMeters.tsx
 * @description A run's totals against the per-run limits (F2).
 */
import React from "react";

import type { Meter } from "@/lib/nucleo/runs";

import styles from "./control.module.css";

export default function RunMeters({ items, label }: { items: Meter[]; label: string }) {
    return (
        <ul className={styles.meters} aria-label={label}>
            {items.map((item) => (
                <li key={item.key} data-level={item.level}>
                    <span>{item.label}</span>
                    <span className={styles.bar} aria-hidden="true">
                        <i style={{ width: `${item.ratio * 100}%` }} />
                    </span>
                    <span className={styles.meterText}>{item.text}</span>
                </li>
            ))}
        </ul>
    );
}
