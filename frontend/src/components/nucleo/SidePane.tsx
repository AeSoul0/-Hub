/**
 * @file frontend/src/components/nucleo/SidePane.tsx
 * @description A side pane of the Nucleo. Its top edge drags up and down
 * (Y only) up to just below the top bar; the arrow keys do the same and a
 * double click restores the standard height. Every page load starts at the
 * standard height.
 */
"use client";

import React, { useEffect, useRef, useState } from "react";

import styles from "./nucleo.module.css";

export const MIN_HEIGHT = 140;
// Room left under the top bar when a pane is at full height.
export const CEILING_GAP = 18;
const KEY_STEP = 24;

/** The height a drag asks for, kept between the minimum and the ceiling. */
export function clampHeight(wanted: number, max: number): number {
    return Math.round(Math.max(MIN_HEIGHT, Math.min(Math.max(MIN_HEIGHT, max), wanted)));
}

/** The tallest a pane may grow: up to just below the ceiling element. */
function ceilingFor(pane: HTMLElement | null, ceiling: HTMLElement | null): number {
    const box = pane?.getBoundingClientRect();
    const top = ceiling?.getBoundingClientRect().bottom ?? 0;
    return box ? box.bottom - top - CEILING_GAP : MIN_HEIGHT;
}

export default function SidePane({
    id,
    side,
    title,
    count,
    hidden = false,
    ceiling,
    header,
    children,
}: {
    id: string;
    side: "left" | "right";
    title: string;
    count: number;
    /** Replaces the title line, e.g. with tabs; `title` still names the pane. */
    header?: React.ReactNode;
    /** Hidden panes keep their height for when they come back. */
    hidden?: boolean;
    /** The element whose bottom edge the pane may not pass. */
    ceiling: React.RefObject<HTMLElement | null>;
    children: React.ReactNode;
}) {
    const pane = useRef<HTMLElement>(null);
    const [height, setHeight] = useState<number | null>(null);
    const [dragging, setDragging] = useState(false);

    const maxHeight = () => ceilingFor(pane.current, ceiling.current);

    // Keep a custom height inside the window when the window shrinks.
    useEffect(() => {
        if (height === null) {
            return;
        }
        const keep = () =>
            setHeight((current) =>
                current === null ? null : clampHeight(current, ceilingFor(pane.current, ceiling.current)),
            );
        window.addEventListener("resize", keep);
        return () => window.removeEventListener("resize", keep);
    }, [height, ceiling]);

    const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
        const box = pane.current?.getBoundingClientRect();
        if (!box) {
            return;
        }
        event.preventDefault();
        const grip = event.currentTarget;
        grip.setPointerCapture(event.pointerId);
        setDragging(true);
        document.body.style.userSelect = "none";

        const move = (moveEvent: PointerEvent) => setHeight(clampHeight(box.bottom - moveEvent.clientY, maxHeight()));
        const up = () => {
            grip.removeEventListener("pointermove", move);
            setDragging(false);
            document.body.style.userSelect = "";
        };
        grip.addEventListener("pointermove", move);
        grip.addEventListener("pointerup", up, { once: true });
        grip.addEventListener("pointercancel", up, { once: true });
    };

    const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
        if (event.key !== "ArrowUp" && event.key !== "ArrowDown") {
            return;
        }
        event.preventDefault();
        const current = pane.current?.getBoundingClientRect().height ?? MIN_HEIGHT;
        setHeight(clampHeight(current + (event.key === "ArrowUp" ? KEY_STEP : -KEY_STEP), maxHeight()));
    };

    const style = height === null ? undefined : ({ "--h": `${height}px` } as React.CSSProperties);

    return (
        <aside
            ref={pane}
            id={id}
            aria-label={title}
            hidden={hidden}
            className={`${styles.pane} ${side === "left" ? styles.left : styles.right}`}
            style={style}
        >
            <div
                role="separator"
                aria-orientation="horizontal"
                aria-label={`Altezza: ${title.toLowerCase()}`}
                tabIndex={0}
                className={`${styles.grip} ${dragging ? styles.dragging : ""}`}
                onPointerDown={onPointerDown}
                onKeyDown={onKeyDown}
                onDoubleClick={() => setHeight(null)}
            />
            {header ?? (
                <h2 className={styles.paneTitle}>
                    {title.toUpperCase()} <span>{count || ""}</span>
                </h2>
            )}
            {children}
        </aside>
    );
}
