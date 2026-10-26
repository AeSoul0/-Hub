/**
 * @file frontend/src/components/control-plane/SettingsForm.tsx
 * @description Editable settings (M12, restyled in F4): each field shows
 * where its value comes from; Save sends only what changed, Ripristina goes
 * back to the environment or the default. The backend validates the whole
 * batch.
 */
import React, { useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import type { SettingChanges, SettingField } from "@/lib/api/settings";
import { settingText, SOURCE_LABELS } from "@/lib/nucleo/models";

const CHOICE_EMPTY: Record<string, string> = {
    AEHUB_FORCE_ROLE: "per regole (consigliato)",
};

export default function SettingsForm({
    fields,
    errors,
    busy,
    onSave,
    submitLabel = "Salva",
}: {
    fields: SettingField[];
    errors: Record<string, string>;
    busy: boolean;
    onSave: (changes: SettingChanges) => void;
    submitLabel?: string;
}) {
    const [draft, setDraft] = useState<Record<string, string>>(() =>
        Object.fromEntries(fields.map((field) => [field.name, field.value])),
    );

    const changes: SettingChanges = Object.fromEntries(
        fields
            .filter((field) => (draft[field.name] ?? "") !== field.value)
            .map((field) => [field.name, draft[field.name] ?? ""]),
    );

    const set = (name: string, value: string) => setDraft((current) => ({ ...current, [name]: value }));

    return (
        <form
            onSubmit={(event) => {
                event.preventDefault();
                onSave(changes);
            }}
            className={styles.form}
        >
            {fields.map((field) => {
                const id = `setting-${field.name}`;
                const { label, help } = settingText(field);
                const multiline = field.kind === "roles" || field.kind === "prices";
                const common = {
                    id,
                    value: draft[field.name] ?? "",
                    "aria-invalid": Boolean(errors[field.name]),
                    "aria-describedby": `${id}-help`,
                    className: styles.input,
                };

                return (
                    <div key={field.name} className={styles.setting}>
                        <div className={styles.settingHead}>
                            <label htmlFor={id} className={styles.settingLabel}>
                                {label}
                            </label>
                            <span className={styles.source}>{SOURCE_LABELS[field.source]}</span>
                            {field.source === "database" && (
                                <button
                                    type="button"
                                    onClick={() => onSave({ [field.name]: null })}
                                    disabled={busy}
                                    className={styles.linkBtn}
                                    aria-label={`Ripristina ${label}`}
                                >
                                    ripristina
                                </button>
                            )}
                        </div>
                        {field.kind === "choice" ? (
                            <select {...common} onChange={(event) => set(field.name, event.target.value)}>
                                {field.default === "" && <option value="">{CHOICE_EMPTY[field.name] ?? "—"}</option>}
                                {(field.options ?? []).map((option) => (
                                    <option key={option} value={option}>
                                        {option}
                                    </option>
                                ))}
                            </select>
                        ) : multiline ? (
                            <textarea {...common} rows={4} onChange={(event) => set(field.name, event.target.value)} />
                        ) : (
                            <input
                                {...common}
                                inputMode={field.kind === "text" || field.kind === "price_pair" ? undefined : "decimal"}
                                placeholder={field.default}
                                spellCheck={false}
                                onChange={(event) => set(field.name, event.target.value)}
                            />
                        )}
                        <p id={`${id}-help`} className={styles.help}>
                            {help}
                        </p>
                        {errors[field.name] && (
                            <p className={styles.error} role="alert">
                                {errors[field.name]}
                            </p>
                        )}
                    </div>
                );
            })}
            <div className={styles.row}>
                <button
                    type="submit"
                    disabled={busy || Object.keys(changes).length === 0}
                    className={`${styles.btn} ${styles.go}`}
                >
                    {submitLabel}
                </button>
            </div>
        </form>
    );
}
