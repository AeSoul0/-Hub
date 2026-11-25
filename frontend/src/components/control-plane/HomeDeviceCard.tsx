/**
 * @file frontend/src/components/control-plane/HomeDeviceCard.tsx
 * @description One home device on the Home page (F7): what is known of its
 * state, its commands and, for a device declared here, edit and remove.
 *
 * Opening a door is the only action with a second step: the confirmation is
 * recorded as the approval of that call.
 */
"use client";

import React, { useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import { ACTION_TOOL, knownState, type HomeAction, type HomeDevice, type HomeToolStatus } from "@/lib/api/home";
import { catalog, useLanguage } from "@/lib/i18n";
import { FORMAT_LABEL, stateLabel, stateSource, stateTone, TYPE_LABEL } from "@/lib/nucleo/home";

const TEXT = catalog({
    en: {
        fromFile: "from the file",
        addedHere: "added from here",
        turnOnLabel: (name: string) => `Turn on ${name}`,
        turnOn: "Turn on",
        turnOffLabel: (name: string) => `Turn off ${name}`,
        turnOff: "Turn off",
        brightness: "Brightness",
        reallyOpen: (name: string) => `Really open ${name}? This confirmation stays in the log as the approval.`,
        confirmOpen: "Confirm: open",
        cancel: "Cancel",
        lockLabel: (name: string) => `Lock ${name}`,
        lock: "Lock",
        openLabel: (name: string) => `Open ${name}`,
        open: "Open",
        toolOff: "Off in TOOLS: it does not start from here.",
        readLabel: (name: string) => `Read the state of ${name}`,
        read: "Read the state",
        confirmRemove: "Confirm: remove",
        editLabel: (name: string) => `Edit ${name}`,
        edit: "Edit",
        removeLabel: (name: string) => `Remove ${name}`,
        remove: "Remove",
    },
    it: {
        fromFile: "dal file",
        addedHere: "aggiunto da qui",
        turnOnLabel: (name: string) => `Accendi ${name}`,
        turnOn: "Accendi",
        turnOffLabel: (name: string) => `Spegni ${name}`,
        turnOff: "Spegni",
        brightness: "Luminosità",
        reallyOpen: (name: string) =>
            `Apri davvero ${name}? Questa conferma resta nel registro come approvazione.`,
        confirmOpen: "Conferma: apri",
        cancel: "Annulla",
        lockLabel: (name: string) => `Chiudi a chiave ${name}`,
        lock: "Chiudi a chiave",
        openLabel: (name: string) => `Apri ${name}`,
        open: "Apri",
        toolOff: "Spento in STRUMENTI: da qui non parte.",
        readLabel: (name: string) => `Leggi lo stato di ${name}`,
        read: "Leggi lo stato",
        confirmRemove: "Conferma: togli",
        editLabel: (name: string) => `Modifica ${name}`,
        edit: "Modifica",
        removeLabel: (name: string) => `Togli ${name}`,
        remove: "Togli",
    },
});

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
    const lang = useLanguage();
    const t = TEXT[lang];
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
                    {stateLabel(known, lang)}
                </span>
            </div>

            <p className={styles.muted}>
                {TYPE_LABEL[lang][device.type]} · {FORMAT_LABEL[device.format]} ·{" "}
                {device.source === "file" ? t.fromFile : t.addedHere}
            </p>
            <p className={styles.deviceTopic}>{device.topic}</p>
            <p className={styles.help}>{stateSource(known, lang)}</p>

            {device.type === "light" ? (
                <>
                    <div className={styles.row}>
                        <button
                            type="button"
                            className={styles.btn}
                            disabled={blocked("on")}
                            aria-label={t.turnOnLabel(device.name)}
                            onClick={() => onCommand(device, "on", level === null ? undefined : { brightness: level })}
                        >
                            {t.turnOn}
                        </button>
                        <button
                            type="button"
                            className={styles.btn}
                            disabled={blocked("off")}
                            aria-label={t.turnOffLabel(device.name)}
                            onClick={() => onCommand(device, "off")}
                        >
                            {t.turnOff}
                        </button>
                    </div>
                    {device.format === "zigbee2mqtt" && (
                        <label className={styles.field}>
                            {t.brightness}
                            {level === null ? "" : ` ${level}%`}
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
                    <p className={styles.warn}>{t.reallyOpen(device.name)}</p>
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
                            {t.confirmOpen}
                        </button>
                        <button type="button" className={styles.linkBtn} onClick={() => setConfirmingOpen(false)}>
                            {t.cancel}
                        </button>
                    </div>
                </div>
            ) : (
                <div className={styles.row}>
                    <button
                        type="button"
                        className={styles.btn}
                        disabled={blocked("lock")}
                        aria-label={t.lockLabel(device.name)}
                        onClick={() => onCommand(device, "lock")}
                    >
                        {t.lock}
                    </button>
                    <button
                        type="button"
                        className={`${styles.btn} ${styles.danger}`}
                        disabled={blocked("unlock")}
                        aria-label={t.openLabel(device.name)}
                        onClick={() => setConfirmingOpen(true)}
                    >
                        {t.open}
                    </button>
                </div>
            )}

            {actions.some(off) && <p className={styles.warn}>{t.toolOff}</p>}

            <div className={styles.row}>
                <button
                    type="button"
                    className={styles.linkBtn}
                    disabled={busy || offline}
                    aria-label={t.readLabel(device.name)}
                    onClick={() => onRead(device)}
                >
                    {t.read}
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
                                {t.confirmRemove}
                            </button>
                            <button type="button" className={styles.linkBtn} onClick={() => setConfirmingRemove(false)}>
                                {t.cancel}
                            </button>
                        </>
                    ) : (
                        <>
                            <button
                                type="button"
                                className={styles.linkBtn}
                                disabled={busy}
                                aria-label={t.editLabel(device.name)}
                                onClick={() => onEdit(device)}
                            >
                                {t.edit}
                            </button>
                            <button
                                type="button"
                                className={styles.linkBtn}
                                disabled={busy}
                                aria-label={t.removeLabel(device.name)}
                                onClick={() => setConfirmingRemove(true)}
                            >
                                {t.remove}
                            </button>
                        </>
                    ))}
            </div>
        </li>
    );
}
