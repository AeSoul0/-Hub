/**
 * @file frontend/src/components/control-plane/RoleEditor.tsx
 * @description The LLM of each role (F4): Architect, Research, Critic (the
 * supervisor), Fast Worker and Triage, each with its chain of models, the
 * first one first and the others as fallbacks.
 *
 * A role left on "default" uses the default model (OPENAI_MODEL, or the
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
    offeredProviders,
    ROLE_INFO,
    ROLES,
    rolesJson,
    type Chains,
    type Target,
} from "@/lib/nucleo/models";
import { catalog, useLanguage } from "@/lib/i18n";

const TEXT = catalog({
    en: {
        intro:
            "The role of each task is chosen by rules from its text, without calling a model. Each role tries its models in order: the first, then the fallbacks if the first does not answer.",
        noList: (providers: string) => `No model list for ${providers}: type the name by hand.`,
        custom: "custom",
        default: "default",
        providerOf: (index: number, role: string) => `Provider ${index} of ${role}`,
        modelOf: (index: number, role: string) => `Model ${index} of ${role}`,
        modelName: "model name",
        theModel: "the model",
        moveUp: (model: string) => `Move up ${model}`,
        moveDown: (model: string) => `Move down ${model}`,
        remove: (model: string) => `Remove ${model}`,
        keyMissing: (providers: string) => `The key of ${providers} is missing.`,
        addFallback: "+ fallback model",
        backToDefault: "back to the default",
        customize: "Customize",
        criticClash: (clashes: string) => `The Critic must use models different from the other roles: ${clashes}.`,
        clash: (model: string, role: string) => `${model} is also in ${role}`,
        noModel: (roles: string) => `No model in: ${roles}.`,
        save: "Save the models",
        cancel: "Cancel",
        json: "JSON that will be saved",
        noCustom: "(no custom role)",
    },
    it: {
        intro:
            "Il ruolo di ogni compito si sceglie per regole dal testo, senza chiamare un modello. Ogni ruolo prova i suoi modelli in ordine: il primo, poi le riserve se il primo non risponde.",
        noList: (providers: string) => `Elenco dei modelli non disponibile per ${providers}: scrivi il nome a mano.`,
        custom: "personalizzato",
        default: "predefinito",
        providerOf: (index: number, role: string) => `Provider ${index} di ${role}`,
        modelOf: (index: number, role: string) => `Modello ${index} di ${role}`,
        modelName: "nome del modello",
        theModel: "il modello",
        moveUp: (model: string) => `Sposta su ${model}`,
        moveDown: (model: string) => `Sposta giù ${model}`,
        remove: (model: string) => `Togli ${model}`,
        keyMissing: (providers: string) => `Manca la chiave di ${providers}.`,
        addFallback: "+ modello di riserva",
        backToDefault: "torna al predefinito",
        customize: "Personalizza",
        criticClash: (clashes: string) => `Il Critic deve usare modelli diversi dagli altri ruoli: ${clashes}.`,
        clash: (model: string, role: string) => `${model} è anche in ${role}`,
        noModel: (roles: string) => `Manca il modello in: ${roles}.`,
        save: "Salva i modelli",
        cancel: "Annulla",
        json: "JSON che verrà salvato",
        noCustom: "(nessun ruolo personalizzato)",
    },
});

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
    const lang = useLanguage();
    const t = TEXT[lang];
    const roleInfo = ROLE_INFO[lang];
    const providerLabels = PROVIDER_LABELS[lang];
    const [chains, setChains] = useState<Chains>(() => initialChains(view));
    const [custom, setCustom] = useState<Record<RoleName, boolean>>(() => initialCustom(view));
    // Newer providers appear once they have a key (P1, ADR-032).
    const offered = offeredProviders(
        view.providers,
        ROLES.flatMap((role) => initialChains(view)[role].map((target) => target.provider)),
    );
    const { models, missing } = useProviderModels(offered);

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
            <p className={styles.help}>{t.intro}</p>

            {offered.filter((provider) => missing[provider]).length > 0 && (
                <p className={styles.help}>
                    {t.noList(
                        offered
                            .filter((provider) => missing[provider])
                            .map((provider) => providerLabels[provider])
                            .join(", "),
                    )}
                </p>
            )}

            {offered.map((provider) => (
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
                            aria-label={roleInfo[role].title}
                        >
                            <div className={styles.row}>
                                <h3 className={styles.h2} style={{ margin: 0 }}>
                                    {roleInfo[role].title}
                                </h3>
                                <span className={styles.badge} data-tone={editable ? "live" : undefined}>
                                    {editable ? t.custom : t.default}
                                </span>
                            </div>
                            <p className={styles.help}>{roleInfo[role].job}</p>
                            <ol className={styles.chain}>
                                {chain.map((target, index) => (
                                    <li
                                        key={index}
                                        data-conflict={conflictModels.has(target.model.trim()) || undefined}
                                    >
                                        <select
                                            className={styles.input}
                                            aria-label={t.providerOf(index + 1, roleInfo[role].title)}
                                            value={target.provider}
                                            disabled={!editable}
                                            onChange={(event) =>
                                                setTarget(role, index, { provider: event.target.value as ProviderName })
                                            }
                                        >
                                            {offered.map((provider) => (
                                                <option key={provider} value={provider}>
                                                    {providerLabels[provider]}
                                                </option>
                                            ))}
                                        </select>
                                        <input
                                            className={styles.input}
                                            aria-label={t.modelOf(index + 1, roleInfo[role].title)}
                                            list={`models-${target.provider}`}
                                            value={target.model}
                                            disabled={!editable}
                                            spellCheck={false}
                                            placeholder={t.modelName}
                                            onChange={(event) => setTarget(role, index, { model: event.target.value })}
                                        />
                                        {editable && (
                                            <span className={styles.icons}>
                                                <button
                                                    type="button"
                                                    className={styles.icon}
                                                    aria-label={t.moveUp(target.model || t.theModel)}
                                                    disabled={index === 0}
                                                    onClick={() => move(role, index, -1)}
                                                >
                                                    ↑
                                                </button>
                                                <button
                                                    type="button"
                                                    className={styles.icon}
                                                    aria-label={t.moveDown(target.model || t.theModel)}
                                                    disabled={index === chain.length - 1}
                                                    onClick={() => move(role, index, 1)}
                                                >
                                                    ↓
                                                </button>
                                                <button
                                                    type="button"
                                                    className={styles.icon}
                                                    aria-label={t.remove(target.model || t.theModel)}
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
                                    {t.keyMissing(
                                        [
                                            ...new Set(
                                                chain
                                                    .filter((target) => keyMissing(target.provider))
                                                    .map((target) => providerLabels[target.provider]),
                                            ),
                                        ].join(", "),
                                    )}
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
                                            {t.addFallback}
                                        </button>
                                        <button
                                            type="button"
                                            className={styles.linkBtn}
                                            onClick={() => {
                                                setCustom((current) => ({ ...current, [role]: false }));
                                                setChains((current) => ({ ...current, [role]: initialChains(view)[role] }));
                                            }}
                                        >
                                            {t.backToDefault}
                                        </button>
                                    </>
                                ) : (
                                    <button
                                        type="button"
                                        className={styles.btn}
                                        onClick={() => setCustom((current) => ({ ...current, [role]: true }))}
                                    >
                                        {t.customize}
                                    </button>
                                )}
                            </div>
                        </section>
                    );
                })}
            </div>

            {conflicts.length > 0 && (
                <p className={styles.error} role="alert">
                    {t.criticClash(
                        conflicts.map((entry) => t.clash(entry.model, roleInfo[entry.role].title)).join("; "),
                    )}
                </p>
            )}
            {empty.length > 0 && (
                <p className={styles.error} role="alert">
                    {t.noModel(empty.map((role) => roleInfo[role].title).join(", "))}
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
                    {t.save}
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
                        {t.cancel}
                    </button>
                )}
            </div>

            <details className={styles.details}>
                <summary>{t.json}</summary>
                <pre className={styles.pre}>{json ? JSON.stringify(JSON.parse(json), null, 2) : t.noCustom}</pre>
            </details>
        </div>
    );
}
