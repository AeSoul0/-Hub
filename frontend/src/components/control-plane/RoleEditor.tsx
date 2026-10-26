/**
 * @file frontend/src/components/control-plane/RoleEditor.tsx
 * @description The LLM of each role (F4): Architect, Research, Critic (the
 * supervisor), Fast Worker and Triage, each with its chain of models, the
 * first one first and the others as fallbacks.
 *
 * A role left on "predefinito" uses the default model (OPENAI_MODEL, or the
 * default Critic). Saving writes AEHUB_MODEL_ROLES with the custom roles
 * only. Model names are suggested from each provider's list but can be
 * typed freely. The Critic must not share a model with another role: the
 * editor marks the clash and does not save, and the backend refuses it too.
 */
"use client";

import React, { useMemo, useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import {
    useProviderModels,
    type ProviderModel,
    type ProviderName,
    type RoleName,
    type SettingChanges,
    type SettingsView,
} from "@/lib/api/settings";
import {
    contextLabel,
    criticConflicts,
    emptyRoles,
    parseTarget,
    PROVIDER_LABELS,
    PROVIDERS,
    ROLE_INFO,
    ROLES,
    rolesJson,
    type Chains,
    type Target,
} from "@/lib/nucleo/models";

function initialChains(view: SettingsView): Chains {
    return Object.fromEntries(
        ROLES.map((role) => [role, (view.roles[role]?.chain ?? []).map(parseTarget)]),
    ) as Chains;
}

function initialCustom(view: SettingsView): Record<RoleName, boolean> {
    return Object.fromEntries(ROLES.map((role) => [role, Boolean(view.roles[role]?.custom)])) as Record<
        RoleName,
        boolean
    >;
}

function optionLabel(model: ProviderModel): string {
    const parts = [model.name !== model.id ? model.name : ""];
    if (model.price) {
        parts.push(`$${model.price.input}/$${model.price.output} per 1M`);
    }
    if (model.context) {
        parts.push(contextLabel(model.context));
    }
    return parts.filter(Boolean).join(" · ");
}

export default function RoleEditor({
    view,
    busy,
    onSave,
    error,
}: {
    view: SettingsView;
    busy: boolean;
    onSave: (changes: SettingChanges) => void;
    /** The backend's routing error of the last save, if any. */
    error?: string;
}) {
    const [chains, setChains] = useState<Chains>(() => initialChains(view));
    const [custom, setCustom] = useState<Record<RoleName, boolean>>(() => initialCustom(view));
    const { models, missing } = useProviderModels(PROVIDERS);

    const json = rolesJson(chains, custom);
    // Compared in the same form, so spacing or key order of the saved JSON
    // does not count as a change.
    const dirty = json !== rolesJson(initialChains(view), initialCustom(view));
    const conflicts = useMemo(() => criticConflicts(chains), [chains]);
    const empty = emptyRoles(chains, custom);
    const conflictModels = new Set(conflicts.map((entry) => entry.model));

    const edit = (role: RoleName, change: (chain: Target[]) => Target[]) =>
        setChains((current) => ({ ...current, [role]: change([...current[role]]) }));

    const setTarget = (role: RoleName, index: number, target: Partial<Target>) =>
        edit(role, (chain) => chain.map((entry, at) => (at === index ? { ...entry, ...target } : entry)));

    const move = (role: RoleName, index: number, by: number) =>
        edit(role, (chain) => {
            const [entry] = chain.splice(index, 1);
            chain.splice(index + by, 0, entry);
            return chain;
        });

    const keyMissing = (provider: ProviderName) =>
        view.providers[provider]?.needs_key && !view.providers[provider]?.key;

    return (
        <div className={styles.stack} style={{ gap: 16 }}>
            <p className={styles.help}>
                Il ruolo di ogni compito si sceglie per regole dal testo, senza chiamare un modello. Ogni ruolo prova i
                suoi modelli in ordine: il primo, poi le riserve se il primo non risponde.
            </p>

            {PROVIDERS.filter((provider) => missing[provider]).length > 0 && (
                <p className={styles.help}>
                    Elenco dei modelli non disponibile per{" "}
                    {PROVIDERS.filter((provider) => missing[provider])
                        .map((provider) => PROVIDER_LABELS[provider])
                        .join(", ")}
                    : scrivi il nome a mano.
                </p>
            )}

            {PROVIDERS.map((provider) => (
                <datalist key={provider} id={`models-${provider}`}>
                    {(models[provider] ?? []).map((model) => (
                        <option key={model.id} value={model.id} label={optionLabel(model)} />
                    ))}
                </datalist>
            ))}

            <div className={styles.roles}>
                {ROLES.map((role) => {
                    const editable = custom[role];
                    const chain = chains[role];
                    return (
                        <section
                            key={role}
                            className={`${styles.card} ${styles.role} ${role === "critic" ? styles.amber : ""}`}
                            data-custom={editable}
                            aria-label={ROLE_INFO[role].title}
                        >
                            <div className={styles.row}>
                                <h3 className={styles.h2} style={{ margin: 0 }}>
                                    {ROLE_INFO[role].title}
                                </h3>
                                <span className={styles.badge} data-tone={editable ? "live" : undefined}>
                                    {editable ? "personalizzato" : "predefinito"}
                                </span>
                            </div>
                            <p className={styles.help}>{ROLE_INFO[role].job}</p>
                            <ol className={styles.chain}>
                                {chain.map((target, index) => (
                                    <li
                                        key={index}
                                        data-conflict={conflictModels.has(target.model.trim()) || undefined}
                                    >
                                        <select
                                            className={styles.input}
                                            aria-label={`Provider ${index + 1} di ${ROLE_INFO[role].title}`}
                                            value={target.provider}
                                            disabled={!editable}
                                            onChange={(event) =>
                                                setTarget(role, index, { provider: event.target.value as ProviderName })
                                            }
                                        >
                                            {PROVIDERS.map((provider) => (
                                                <option key={provider} value={provider}>
                                                    {PROVIDER_LABELS[provider]}
                                                </option>
                                            ))}
                                        </select>
                                        <input
                                            className={styles.input}
                                            aria-label={`Modello ${index + 1} di ${ROLE_INFO[role].title}`}
                                            list={`models-${target.provider}`}
                                            value={target.model}
                                            disabled={!editable}
                                            spellCheck={false}
                                            placeholder="nome del modello"
                                            onChange={(event) => setTarget(role, index, { model: event.target.value })}
                                        />
                                        {editable && (
                                            <span className={styles.icons}>
                                                <button
                                                    type="button"
                                                    className={styles.icon}
                                                    aria-label={`Sposta su ${target.model || "il modello"}`}
                                                    disabled={index === 0}
                                                    onClick={() => move(role, index, -1)}
                                                >
                                                    ↑
                                                </button>
                                                <button
                                                    type="button"
                                                    className={styles.icon}
                                                    aria-label={`Sposta giù ${target.model || "il modello"}`}
                                                    disabled={index === chain.length - 1}
                                                    onClick={() => move(role, index, 1)}
                                                >
                                                    ↓
                                                </button>
                                                <button
                                                    type="button"
                                                    className={styles.icon}
                                                    aria-label={`Togli ${target.model || "il modello"}`}
                                                    disabled={chain.length === 1}
                                                    onClick={() => edit(role, (current) => current.filter((_, at) => at !== index))}
                                                >
                                                    ✕
                                                </button>
                                            </span>
                                        )}
                                    </li>
                                ))}
                            </ol>
                            {chain.some((target) => keyMissing(target.provider)) && (
                                <p className={styles.warn}>
                                    Manca la chiave di{" "}
                                    {[...new Set(chain.filter((target) => keyMissing(target.provider)).map((target) => PROVIDER_LABELS[target.provider]))].join(", ")}
                                    .
                                </p>
                            )}
                            <div className={styles.row}>
                                {editable ? (
                                    <>
                                        <button
                                            type="button"
                                            className={styles.btn}
                                            onClick={() =>
                                                edit(role, (current) => [
                                                    ...current,
                                                    { provider: current[current.length - 1]?.provider ?? "openrouter", model: "" },
                                                ])
                                            }
                                        >
                                            + modello di riserva
                                        </button>
                                        <button
                                            type="button"
                                            className={styles.linkBtn}
                                            onClick={() => {
                                                setCustom((current) => ({ ...current, [role]: false }));
                                                setChains((current) => ({ ...current, [role]: initialChains(view)[role] }));
                                            }}
                                        >
                                            torna al predefinito
                                        </button>
                                    </>
                                ) : (
                                    <button
                                        type="button"
                                        className={styles.btn}
                                        onClick={() => setCustom((current) => ({ ...current, [role]: true }))}
                                    >
                                        Personalizza
                                    </button>
                                )}
                            </div>
                        </section>
                    );
                })}
            </div>

            {conflicts.length > 0 && (
                <p className={styles.error} role="alert">
                    Il Critic deve usare modelli diversi dagli altri ruoli:{" "}
                    {conflicts.map((entry) => `${entry.model} è anche in ${ROLE_INFO[entry.role].title}`).join("; ")}.
                </p>
            )}
            {empty.length > 0 && (
                <p className={styles.error} role="alert">
                    Manca il modello in: {empty.map((role) => ROLE_INFO[role].title).join(", ")}.
                </p>
            )}
            {error && (
                <p className={styles.error} role="alert">
                    {error}
                </p>
            )}

            <div className={styles.row}>
                <button
                    type="button"
                    className={`${styles.btn} ${styles.go}`}
                    disabled={busy || !dirty || conflicts.length > 0 || empty.length > 0}
                    onClick={() => onSave({ AEHUB_MODEL_ROLES: json || null })}
                >
                    Salva i modelli
                </button>
                {dirty && (
                    <button
                        type="button"
                        className={styles.btn}
                        onClick={() => {
                            setChains(initialChains(view));
                            setCustom(initialCustom(view));
                        }}
                    >
                        Annulla
                    </button>
                )}
            </div>

            <details className={styles.details}>
                <summary>JSON che verrà salvato</summary>
                <pre className={styles.pre}>{json ? JSON.stringify(JSON.parse(json), null, 2) : "(nessun ruolo personalizzato)"}</pre>
            </details>
        </div>
    );
}
