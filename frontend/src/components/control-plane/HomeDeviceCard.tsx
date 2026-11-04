/**
 * @file frontend/src/components/control-plane/HomeDeviceCard.tsx
 * @description One home device on the CASA page (F7): what is known of its
 * state, its commands and, for a device declared here, edit and remove.
 *
 * Opening a door is the only action with a second step: the confirmation is
 * recorded as the approval of that call.
 */
"use client";

import React, { useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import { ACTION_TOOL, knownState, type HomeAction, type HomeDevice, type HomeToolStatus } from "@/lib/api/home";
import { FORMAT_LABEL, stateLabel, stateSource, stateTone, TYPE_LABEL } from "@/lib/nucleo/home";

interface HomeDeviceCardProps {
    device: HomeDevice;
    busy: boolean;
    tools: Record<string, HomeToolStatus>;
    /** No broker configured: nothing can be sent or asked. */
    offline: boolean;
    onCommand: (device: HomeDevice, action: HomeAction, options?: { brightness?: number; confirm?: boolean }) => void;
    onRead: (device: HomeDevice) => void;
    onEdit: (device: HomeDevice) => void;
    onRemove: (device: HomeDevice) => void;
}

export default function HomeDeviceCard({
    device,
    busy,
    tools,
    offline,
    onCommand,
    onRead,
    onEdit,
    onRemove,
}: HomeDeviceCardProps) {
    const [confirmingOpen, setConfirmingOpen] = useState(false);
    const [confirmingRemove, setConfirmingRemove] = useState(false);
    const [level, setLevel] = useState<number | null>(null);

    const known = knownState(device);
    const off = (action: HomeAction) => tools[ACTION_TOOL[action]]?.disabled === true;
    const blocked = (action: HomeAction) => busy || offline || off(action);
    const actions: HomeAction[] = device.type === "light" ? ["on"] : ["lock", "unlock"];

    return (
        <li className={styles.device} aria-label={device.name}>
            <div className={styles.deviceHead}>
                <span className={styles.deviceName}>{device.name}</span>
                <span className={styles.badge} data-tone={stateTone(known.state)}>
                    {stateLabel(known)}
                </span>
            </div>

            <p className={styles.muted}>
                {TYPE_LABEL[device.type]} · {FORMAT_LABEL[device.format]} ·{" "}
                {device.source === "file" ? "dal file" : "aggiunto da qui"}
            </p>
            <p className={styles.deviceTopic}>{device.topic}</p>
            <p className={styles.help}>{stateSource(known)}</p>

            {device.type === "light" ? (
                <>
                    <div className={styles.row}>
                        <button
                            type="button"
                            className={styles.btn}
                            disabled={blocked("on")}
                            aria-label={`Accendi ${device.name}`}
                            onClick={() => onCommand(device, "on", level === null ? undefined : { brightness: level })}
                        >
                            Accendi
                        </button>
                        <button
                            type="button"
                            className={styles.btn}
                            disabled={blocked("off")}
                            aria-label={`Spegni ${device.name}`}
                            onClick={() => onCommand(device, "off")}
                        >
                            Spegni
                        </button>
                    </div>
                    {device.format === "zigbee2mqtt" && (
                        <label className={styles.field}>
                            Luminosità{level === null ? "" : ` ${level}%`}
                            <input
                                type="range"
                                min={0}
                                max={100}
                                value={level ?? known.brightness ?? 100}
                                onChange={(event) => setLevel(Number(event.target.value))}
                            />
                        </label>
                    )}
                </>
            ) : confirmingOpen ? (
                <div className={styles.stack}>
                    <p className={styles.warn}>
                        Apri davvero {device.name}? Questa conferma resta nel registro come approvazione.
                    </p>
                    <div className={styles.row}>
                        <button
                            type="button"
                            className={`${styles.btn} ${styles.danger}`}
                            disabled={blocked("unlock")}
                            onClick={() => {
                                setConfirmingOpen(false);
                                onCommand(device, "unlock", { confirm: true });
                            }}
                        >
                            Conferma: apri
                        </button>
                        <button type="button" className={styles.linkBtn} onClick={() => setConfirmingOpen(false)}>
                            Annulla
                        </button>
                    </div>
                </div>
            ) : (
                <div className={styles.row}>
                    <button
                        type="button"
                        className={styles.btn}
                        disabled={blocked("lock")}
                        aria-label={`Chiudi a chiave ${device.name}`}
                        onClick={() => onCommand(device, "lock")}
                    >
                        Chiudi a chiave
                    </button>
                    <button
                        type="button"
                        className={`${styles.btn} ${styles.danger}`}
                        disabled={blocked("unlock")}
                        aria-label={`Apri ${device.name}`}
                        onClick={() => setConfirmingOpen(true)}
                    >
                        Apri
                    </button>
                </div>
            )}

            {actions.some(off) && <p className={styles.warn}>Spento in STRUMENTI: da qui non parte.</p>}

            <div className={styles.row}>
                <button
                    type="button"
                    className={styles.linkBtn}
                    disabled={busy || offline}
                    aria-label={`Leggi lo stato di ${device.name}`}
                    onClick={() => onRead(device)}
                >
                    Leggi lo stato
                </button>
                {device.source === "app" &&
                    (confirmingRemove ? (
                        <>
                            <button
                                type="button"
                                className={`${styles.btn} ${styles.danger}`}
                                disabled={busy}
                                onClick={() => onRemove(device)}
                            >
                                Conferma: togli
                            </button>
                            <button type="button" className={styles.linkBtn} onClick={() => setConfirmingRemove(false)}>
                                Annulla
                            </button>
                        </>
                    ) : (
                        <>
                            <button
                                type="button"
                                className={styles.linkBtn}
                                disabled={busy}
                                aria-label={`Modifica ${device.name}`}
                                onClick={() => onEdit(device)}
                            >
                                Modifica
                            </button>
                            <button
                                type="button"
                                className={styles.linkBtn}
                                disabled={busy}
                                aria-label={`Togli ${device.name}`}
                                onClick={() => setConfirmingRemove(true)}
                            >
                                Togli
                            </button>
                        </>
                    ))}
            </div>
        </li>
    );
}
