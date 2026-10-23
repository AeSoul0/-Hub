/**
 * @file frontend/src/components/control-plane/SettingsForm.tsx
 * @description Editable settings (M12): each field shows where its value
 * comes from; Save sends only what changed, Reset goes back to the
 * environment or the default. The backend validates the whole batch.
 */
import React, { useState } from "react";

import type { SettingChanges, SettingField, SettingSource } from "@/lib/api/settings";

const SOURCE_LABEL: Record<SettingSource, string> = {
    database: "set here",
    environment: "from backend/.env",
    default: "default",
};

export default function SettingsForm({
    fields,
    errors,
    busy,
    onSave,
    submitLabel = "Save",
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

    return (
        <form
            onSubmit={(event) => {
                event.preventDefault();
                onSave(changes);
            }}
            className="space-y-4 max-w-3xl"
        >
            {fields.map((field) => {
                const id = `setting-${field.name}`;
                const multiline = field.kind === "roles" || field.kind === "prices";
                const common = {
                    id,
                    value: draft[field.name] ?? "",
                    "aria-invalid": Boolean(errors[field.name]),
                    "aria-describedby": `${id}-help`,
                    className: `w-full rounded bg-gray-900 border px-3 py-1 ${
                        errors[field.name] ? "border-red-600" : "border-gray-700"
                    } ${multiline ? "font-mono text-sm" : ""}`,
                };

                return (
                    <div key={field.name}>
                        <div className="flex flex-wrap items-baseline gap-2 mb-1">
                            <label htmlFor={id} className="text-sm text-gray-200">
                                {field.label}
                            </label>
                            <span className="text-xs text-gray-500">{SOURCE_LABEL[field.source]}</span>
                            {field.source === "database" && (
                                <button
                                    type="button"
                                    onClick={() => onSave({ [field.name]: null })}
                                    disabled={busy}
                                    className="text-xs text-cyan-400 hover:text-cyan-300"
                                    aria-label={`Reset ${field.label}`}
                                >
                                    Reset
                                </button>
                            )}
                        </div>
                        {multiline ? (
                            <textarea
                                {...common}
                                rows={4}
                                onChange={(event) =>
                                    setDraft((current) => ({ ...current, [field.name]: event.target.value }))
                                }
                            />
                        ) : (
                            <input
                                {...common}
                                inputMode={field.kind === "text" || field.kind === "price_pair" ? undefined : "decimal"}
                                placeholder={field.default}
                                onChange={(event) =>
                                    setDraft((current) => ({ ...current, [field.name]: event.target.value }))
                                }
                            />
                        )}
                        <p id={`${id}-help`} className="mt-1 text-xs text-gray-400">
                            {field.help}
                        </p>
                        {errors[field.name] && <p className="text-sm text-red-400">{errors[field.name]}</p>}
                    </div>
                );
            })}
            <button
                type="submit"
                disabled={busy || Object.keys(changes).length === 0}
                className="bg-orange-600 hover:bg-orange-500 disabled:opacity-50 rounded px-4 py-1"
            >
                {submitLabel}
            </button>
        </form>
    );
}
