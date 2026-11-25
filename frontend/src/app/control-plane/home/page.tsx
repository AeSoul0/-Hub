/**
 * @file frontend/src/app/control-plane/home/page.tsx
 * @description Home (F7, ADR-021, ADR-028): the devices, their commands and
 * the broker.
 *
 * Reads GET /api/home and the "home" group of GET /api/settings. The broker
 * address and user save through PUT /api/settings, the password goes to the
 * OS keyring (PUT /api/desktop/secrets) and is never shown again. A command
 * is the agent's own tool through the Tool Gateway. The devices of the file
 * AEHUB_HOME_DEVICES are read only; those declared here go to
 * PUT /api/home/devices as one whole list.
 */
"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

import HomeDeviceCard from "@/components/control-plane/HomeDeviceCard";
import styles from "@/components/control-plane/control.module.css";
import { getJson, postJson, putJson } from "@/lib/api/client";
import {
    deviceId,
    ownDevices,
    topicHint,
    withDevice,
    withoutDevice,
    type DeviceEntry,
    type DeviceFormat,
    type DeviceType,
    type HomeAction,
    type HomeDevice,
    type HomeView,
} from "@/lib/api/home";
import { useSettings } from "@/lib/api/settings";
import { catalog, useLanguage, type Lang } from "@/lib/i18n";
import { FORMAT_LABEL, homeError, TYPE_LABEL } from "@/lib/nucleo/home";

const EMPTY: DeviceEntry = { id: "", name: "", type: "light", topic: "", format: "zigbee2mqtt" };

const TEXT = catalog({
    en: {
        device: "Device",
        name: "Name",
        namePlaceholder: "Living room light",
        type: "Type",
        format: "Format",
        topic: "Command topic",
        agentCalls: "The agent calls it",
        agentCallsRest: ": it never sees the topic, so it cannot write elsewhere on the broker.",
        saveDevice: "Save the device",
        add: "Add",
        cancel: "Cancel",
        saved: "Saved: it applies from the next command.",
        notSaved: "Not saved.",
        passwordSaved: "Password saved in the system keyring.",
        brokerOk: "The broker answers.",
        brokerDown: "The broker does not answer.",
        unavailable: "Home not available:",
        loading: "Loading the home…",
        title: "HOME",
        brokerMissing: "broker missing",
        brokerSet: "broker set",
        devices: (count: number) => (count === 1 ? "1 device" : `${count} devices`),
        stopped: "The devices are stopped:",
        devicesTitle: "Devices",
        noDevices: "No devices. Add one below: the home tools appear by themselves.",
        noBroker: "Without a broker the commands do not start: set it below.",
        file: "Devices file, read only:",
        edit: (name: string) => `Edit ${name}`,
        addDevice: "Add a device",
        broker: "MQTT broker",
        address: "Address",
        user: "User",
        save: "Save",
        test: "Test the connection",
        passwordSet: "password set",
        noPassword: "no password",
        password: "Broker password",
        savePassword: "Save the password",
        setWith: "It is set with",
        setWithRest: ", then a restart.",
        passwordHelp: "It stays in the system keyring and cannot be read again from here. It is needed only if the broker has a user.",
    },
    it: {
        device: "Dispositivo",
        name: "Nome",
        namePlaceholder: "Luce del soggiorno",
        type: "Tipo",
        format: "Formato",
        topic: "Topic dei comandi",
        agentCalls: "L'agente lo chiama",
        agentCallsRest: ": non vede mai il topic, quindi non può scrivere altrove sul broker.",
        saveDevice: "Salva il dispositivo",
        add: "Aggiungi",
        cancel: "Annulla",
        saved: "Salvato: vale dal prossimo comando.",
        notSaved: "Non salvato.",
        passwordSaved: "Password salvata nel portachiavi del sistema.",
        brokerOk: "Il broker risponde.",
        brokerDown: "Il broker non risponde.",
        unavailable: "Casa non disponibile:",
        loading: "Carico la casa…",
        title: "CASA",
        brokerMissing: "broker mancante",
        brokerSet: "broker impostato",
        devices: (count: number) => (count === 1 ? "1 dispositivo" : `${count} dispositivi`),
        stopped: "I dispositivi sono fermi:",
        devicesTitle: "Dispositivi",
        noDevices: "Nessun dispositivo. Aggiungine uno qui sotto: gli strumenti della casa compaiono da soli.",
        noBroker: "Senza broker i comandi non partono: impostalo qui sotto.",
        file: "File dei dispositivi, in sola lettura:",
        edit: (name: string) => `Modifica ${name}`,
        addDevice: "Aggiungi un dispositivo",
        broker: "Broker MQTT",
        address: "Indirizzo",
        user: "Utente",
        save: "Salva",
        test: "Prova il collegamento",
        passwordSet: "password impostata",
        noPassword: "nessuna password",
        password: "Password del broker",
        savePassword: "Salva la password",
        setWith: "Si imposta con",
        setWithRest: ", poi un riavvio.",
        passwordHelp: "Resta nel portachiavi del sistema e non si rilegge più da qui. Serve solo se il broker ha un utente.",
    },
});

function message(err: unknown, lang: Lang): string {
    return homeError(err instanceof Error ? err.message : String(err), lang);
}

function DeviceForm({
    editing,
    busy,
    error,
    onSave,
    onCancel,
}: {
    editing: DeviceEntry | null;
    busy: boolean;
    error: string | null;
    onSave: (entry: DeviceEntry) => void;
    onCancel: () => void;
}) {
    const lang = useLanguage();
    const t = TEXT[lang];
    const [form, setForm] = useState<DeviceEntry>(editing ?? EMPTY);
    const id = editing ? editing.id : deviceId(form.name);
    const set = (change: Partial<DeviceEntry>) => setForm((current) => ({ ...current, ...change }));

    const submit = (event: React.FormEvent) => {
        event.preventDefault();
        onSave({ ...form, id, name: form.name.trim(), topic: form.topic.trim() });
    };

    return (
        <form onSubmit={submit} className={styles.stack} aria-label={t.device}>
            <div className={styles.filters}>
                <label className={`${styles.field} ${styles.grow}`}>
                    {t.name}
                    <input
                        value={form.name}
                        maxLength={100}
                        placeholder={t.namePlaceholder}
                        onChange={(event) => set({ name: event.target.value })}
                    />
                </label>
                <label className={styles.field}>
                    {t.type}
                    <select
                        value={form.type}
                        onChange={(event) => {
                            const type = event.target.value as DeviceType;
                            // Tasmota drives lights only.
                            set(type === "lock" ? { type, format: "zigbee2mqtt" } : { type });
                        }}
                    >
                        {(Object.keys(TYPE_LABEL[lang]) as DeviceType[]).map((type) => (
                            <option key={type} value={type}>
                                {TYPE_LABEL[lang][type]}
                            </option>
                        ))}
                    </select>
                </label>
                <label className={styles.field}>
                    {t.format}
                    <select
                        value={form.format}
                        disabled={form.type === "lock"}
                        onChange={(event) => set({ format: event.target.value as DeviceFormat })}
                    >
                        {(Object.keys(FORMAT_LABEL) as DeviceFormat[]).map((format) => (
                            <option key={format} value={format}>
                                {FORMAT_LABEL[format]}
                            </option>
                        ))}
                    </select>
                </label>
            </div>
            <label className={styles.field}>
                {t.topic}
                <input
                    value={form.topic}
                    maxLength={256}
                    placeholder={topicHint(form.format, id)}
                    spellCheck={false}
                    onChange={(event) => set({ topic: event.target.value })}
                />
            </label>
            {id && (
                <p className={styles.help}>
                    {t.agentCalls} <code className={styles.mono}>{id}</code>
                    {t.agentCallsRest}
                </p>
            )}
            {error && (
                <p className={styles.error} role="alert">
                    {error}
                </p>
            )}
            <div className={styles.row}>
                <button type="submit" className={`${styles.btn} ${styles.go}`} disabled={busy || !id || !form.topic.trim()}>
                    {editing ? t.saveDevice : t.add}
                </button>
                {editing && (
                    <button type="button" className={styles.btn} onClick={onCancel}>
                        {t.cancel}
                    </button>
                )}
            </div>
        </form>
    );
}

export default function HomePage() {
    const lang = useLanguage();
    const t = TEXT[lang];
    const { view: settings, error: settingsError, save } = useSettings();
    const [home, setHome] = useState<HomeView | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [url, setUrl] = useState<string | null>(null);
    const [username, setUsername] = useState<string | null>(null);
    const [password, setPassword] = useState("");
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [note, setNote] = useState<string | null>(null);
    const [check, setCheck] = useState<{ ok: boolean; text: string } | null>(null);
    const [busy, setBusy] = useState(false);
    const [problem, setProblem] = useState<{ id: string; text: string } | null>(null);
    const [editing, setEditing] = useState<DeviceEntry | null>(null);
    const [formError, setFormError] = useState<string | null>(null);
    const [formKey, setFormKey] = useState(0);

    const refresh = useCallback(async () => {
        try {
            setHome(await getJson<HomeView>("/api/home"));
            setLoadError(null);
        } catch (err) {
            setLoadError(message(err, lang));
        }
    }, [lang]);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    const saved = useMemo(() => {
        const value = (name: string) => settings?.settings.find((field) => field.name === name)?.value ?? "";
        return { url: value("AEHUB_MQTT_URL"), username: value("AEHUB_MQTT_USERNAME") };
    }, [settings]);

    const urlValue = url ?? saved.url;
    const usernameValue = username ?? saved.username;
    const dirty = urlValue.trim() !== saved.url || usernameValue.trim() !== saved.username;

    const saveBroker = async (event: React.FormEvent) => {
        event.preventDefault();
        setBusy(true);
        const outcome = await save({
            AEHUB_MQTT_URL: urlValue.trim(),
            AEHUB_MQTT_USERNAME: usernameValue.trim(),
        });
        setBusy(false);
        setErrors(outcome.errors);
        setCheck(null);
        setNote(outcome.ok ? t.saved : homeError(outcome.message ?? t.notSaved, lang));
        if (outcome.ok) {
            setUrl(null);
            setUsername(null);
            await refresh();
        }
    };

    const savePassword = async () => {
        if (!password) {
            return;
        }
        setBusy(true);
        try {
            await putJson("/api/desktop/secrets", { AEHUB_MQTT_PASSWORD: password });
            setPassword("");
            setCheck(null);
            setNote(t.passwordSaved);
            await refresh();
        } catch (err) {
            setNote(message(err, lang));
        } finally {
            setBusy(false);
        }
    };

    const checkBroker = async () => {
        setBusy(true);
        setCheck(null);
        try {
            const result = await postJson<{ ok: boolean; error: string | null }>("/api/home/broker/check", {});
            setCheck({
                ok: result.ok,
                text: result.ok ? t.brokerOk : homeError(result.error ?? t.brokerDown, lang),
            });
        } catch (err) {
            setCheck({ ok: false, text: message(err, lang) });
        } finally {
            setBusy(false);
        }
    };

    const runOnDevice = async (device: HomeDevice, path: string, body: unknown) => {
        setBusy(true);
        setProblem(null);
        try {
            const result = await postJson<{ device: HomeDevice }>(path, body);
            setHome((current) =>
                current
                    ? {
                          ...current,
                          devices: current.devices.map((item) => (item.id === device.id ? result.device : item)),
                      }
                    : current,
            );
        } catch (err) {
            setProblem({ id: device.id, text: message(err, lang) });
        } finally {
            setBusy(false);
        }
    };

    const command = (
        device: HomeDevice,
        action: HomeAction,
        options: { brightness?: number; confirm?: boolean } = {},
    ) => runOnDevice(device, `/api/home/devices/${device.id}/command`, { action, ...options });

    const read = (device: HomeDevice) => runOnDevice(device, `/api/home/devices/${device.id}/state`, {});

    const saveList = async (entries: DeviceEntry[]): Promise<boolean> => {
        setBusy(true);
        setFormError(null);
        try {
            setHome(await putJson<HomeView>("/api/home/devices", { devices: entries }));
            return true;
        } catch (err) {
            setFormError(message(err, lang));
            return false;
        } finally {
            setBusy(false);
        }
    };

    const resetForm = () => {
        setEditing(null);
        setFormError(null);
        setFormKey((key) => key + 1);
    };

    const saveDevice = async (entry: DeviceEntry) => {
        if (home && (await saveList(withDevice(ownDevices(home.devices), entry)))) {
            resetForm();
        }
    };

    const removeDevice = async (device: HomeDevice) => {
        if (home) {
            await saveList(withoutDevice(ownDevices(home.devices), device.id));
        }
    };

    if (loadError || settingsError) {
        return (
            <main className={styles.page}>
                <p className={styles.error}>
                    {t.unavailable} {loadError ?? settingsError}
                </p>
            </main>
        );
    }

    if (!home || !settings) {
        return (
            <main className={styles.page}>
                <p className={styles.muted}>{t.loading}</p>
            </main>
        );
    }

    const offline = home.broker.error !== null;
    const deviceError = home.errors.file ?? home.errors.all ?? home.errors.app;
    const fieldError = (name: string) =>
        errors[name] ? (
            <span className={styles.error} role="alert">
                {errors[name]}
            </span>
        ) : null;

    return (
        <main className={styles.page}>
            <div className={styles.head}>
                <h1 className={styles.title}>{t.title}</h1>
                <span className={styles.badge} data-tone={offline ? "warn" : "ok"}>
                    {offline ? t.brokerMissing : t.brokerSet}
                </span>
                <span className={styles.badge}>
                    {t.devices(home.devices.length)}
                </span>
            </div>

            {deviceError && (
                <p className={styles.error} role="alert">
                    {t.stopped} {homeError(deviceError, lang)}
                </p>
            )}

            <section className={styles.card}>
                <h2 className={styles.h2}>{t.devicesTitle}</h2>
                {home.devices.length ? (
                    <ul className={styles.devices}>
                        {home.devices.map((device) => (
                            <React.Fragment key={device.id}>
                                <HomeDeviceCard
                                    device={device}
                                    busy={busy}
                                    tools={home.tools}
                                    offline={offline}
                                    onCommand={command}
                                    onRead={read}
                                    onEdit={({ id, name, type, topic, format }) => {
                                        setEditing({ id, name, type, topic, format });
                                        setFormError(null);
                                        setFormKey((key) => key + 1);
                                    }}
                                    onRemove={removeDevice}
                                />
                                {problem?.id === device.id && (
                                    <li className={styles.error} role="alert">
                                        {device.name}: {problem.text}
                                    </li>
                                )}
                            </React.Fragment>
                        ))}
                    </ul>
                ) : (
                    <p className={styles.muted}>{t.noDevices}</p>
                )}
                {offline && home.devices.length > 0 && (
                    <p className={styles.warn}>{t.noBroker}</p>
                )}
                {home.file && (
                    <p className={styles.help}>
                        {t.file} <code className={styles.mono}>{home.file}</code>
                    </p>
                )}
            </section>

            <section className={styles.card}>
                <h2 className={styles.h2}>{editing ? t.edit(editing.name) : t.addDevice}</h2>
                <DeviceForm
                    key={formKey}
                    editing={editing}
                    busy={busy}
                    error={formError}
                    onSave={saveDevice}
                    onCancel={resetForm}
                />
            </section>

            <section className={styles.card}>
                <h2 className={styles.h2}>{t.broker}</h2>
                <form onSubmit={saveBroker} className={styles.stack} aria-label={t.broker}>
                    <div className={styles.filters}>
                        <label className={`${styles.field} ${styles.grow}`}>
                            {t.address}
                            <input
                                value={urlValue}
                                placeholder="mqtt://192.168.1.10:1883"
                                spellCheck={false}
                                onChange={(event) => {
                                    setUrl(event.target.value);
                                    setNote(null);
                                }}
                            />
                        </label>
                        <label className={styles.field}>
                            {t.user}
                            <input
                                value={usernameValue}
                                autoComplete="off"
                                spellCheck={false}
                                onChange={(event) => {
                                    setUsername(event.target.value);
                                    setNote(null);
                                }}
                            />
                        </label>
                    </div>
                    {fieldError("AEHUB_MQTT_URL")}
                    {fieldError("AEHUB_MQTT_USERNAME")}
                    <div className={styles.row}>
                        <button type="submit" className={`${styles.btn} ${styles.go}`} disabled={busy || !dirty}>
                            {t.save}
                        </button>
                        <button
                            type="button"
                            className={styles.btn}
                            disabled={busy || dirty || offline}
                            onClick={checkBroker}
                        >
                            {t.test}
                        </button>
                        {note && (
                            <span className={styles.muted} role="status">
                                {note}
                            </span>
                        )}
                        {check && (
                            <span className={check.ok ? styles.muted : styles.error} role="status">
                                {check.text}
                            </span>
                        )}
                    </div>
                </form>

                <div className={styles.row}>
                    <span className={styles.badge} data-tone={home.broker.password_set ? "ok" : undefined}>
                        {home.broker.password_set ? t.passwordSet : t.noPassword}
                    </span>
                    {home.desktop ? (
                        <>
                            <label className={styles.field}>
                                {t.password}
                                <input
                                    type="password"
                                    autoComplete="off"
                                    value={password}
                                    onChange={(event) => setPassword(event.target.value)}
                                />
                            </label>
                            <button
                                type="button"
                                className={styles.btn}
                                onClick={savePassword}
                                disabled={busy || !password}
                            >
                                {t.savePassword}
                            </button>
                        </>
                    ) : (
                        <span className={styles.muted}>
                            {t.setWith} <code className={styles.mono}>python scripts/aehub.py setup</code>
                            {t.setWithRest}
                        </span>
                    )}
                </div>
                <p className={styles.help}>{t.passwordHelp}</p>
            </section>
        </main>
    );
}
