/**
 * @file frontend/src/lib/nucleo/models.ts
 * @description Models, keys and limits in the Control Plane (F4): what each
 * role does, the Italian text of every setting, and the role chains the role
 * editor turns into AEHUB_MODEL_ROLES.
 *
 * The role of a task is chosen by rules from its text, without a model; each
 * role then runs on its own chain "provider:model", the first entry first,
 * the others as fallbacks. The Critic (the supervisor) reviews every result
 * and must not share a model with any other role: the backend refuses such a
 * routing, and the editor says so before saving.
 */

import type { ProviderName, RoleName, SettingField, SettingSource } from "@/lib/api/settings";

export const ROLES: RoleName[] = ["architect", "research", "critic", "fast_worker", "triage"];
export const IMPLEMENTER_ROLES: RoleName[] = ["architect", "research", "fast_worker", "triage"];
export const PROVIDERS: ProviderName[] = ["openai", "openrouter", "local"];

export const ROLE_INFO: Record<RoleName, { title: string; job: string }> = {
    architect: { title: "Architect", job: "Compiti lunghi: codice, progettazione, refactoring, debug." },
    research: { title: "Research", job: "Ricerche, analisi e confronti." },
    critic: {
        title: "Critic · supervisore",
        job: "Controlla il risultato di ogni run e lo fa rifare se non va. Usa un modello diverso da tutti gli altri ruoli.",
    },
    fast_worker: { title: "Fast Worker", job: "Lavori ripetitivi: test, documenti, conversioni, estrazioni." },
    triage: { title: "Triage", job: "Richieste brevi e semplici: qui vanno i modelli più economici." },
};

export const PROVIDER_LABELS: Record<ProviderName, string> = {
    openai: "OpenAI",
    openrouter: "OpenRouter",
    local: "Server locale",
};

export const SOURCE_LABELS: Record<SettingSource, string> = {
    database: "impostato qui",
    environment: "da backend/.env",
    default: "predefinito",
};

/** Italian label and help of each setting; the backend's English is the fallback. */
export const SETTING_TEXT: Record<string, { label: string; help: string }> = {
    OPENAI_MODEL: {
        label: "Modello predefinito",
        help: "Modello OpenAI dei ruoli che non hanno una catena propria.",
    },
    AEHUB_CHECKER_MODEL: {
        label: "Critic predefinito",
        help: "Modello che controlla il risultato quando il Critic non ha una catena propria. Deve essere diverso dagli altri.",
    },
    AEHUB_MODEL_ROLES: {
        label: "Catene dei ruoli (JSON)",
        help: 'Ruolo → elenco di "provider:modello", provati in ordine. Lo scrive l\'editor dei ruoli.',
    },
    AEHUB_FORCE_ROLE: {
        label: "Ruolo forzato",
        help: "Ogni compito usa questo ruolo invece di sceglierlo dal testo. Vuoto: per regole.",
    },
    AEHUB_LOCAL_BASE_URL: {
        label: "Server locale",
        help: "Indirizzo del server compatibile OpenAI del provider locale (Ollama, LM Studio, vLLM).",
    },
    AEHUB_MODEL_PRICES: {
        label: "Prezzi (JSON)",
        help: 'Modello → {"input": USD, "output": USD} per 1M di token. Lo scrive la tabella dei prezzi.',
    },
    AEHUB_DEFAULT_MODEL_PRICE: {
        label: "Prezzo di un modello senza prezzo",
        help: "input,output in USD per 1M di token. Alto apposta: senza prezzo la spesa si sovrastima.",
    },
    AEHUB_RUN_MAX_COST: {
        label: "Costo massimo di una run (USD)",
        help: "La run si ferma quando arriva a questo costo. 0 toglie il limite.",
    },
    AEHUB_MONTHLY_BUDGET: {
        label: "Budget mensile (USD)",
        help: "Raggiunta questa spesa nel mese, le nuove run vengono rifiutate. 0 toglie il limite.",
    },
    AEHUB_BUDGET_WARNING_RATIO: {
        label: "Soglia di avviso del budget",
        help: "Frazione del budget mensile che fa scattare l'avviso (tra 0 e 1).",
    },
    AEHUB_RUN_TIMEOUT_SECONDS: {
        label: "Tempo attivo di una run (secondi)",
        help: "L'attesa di un'approvazione non conta. 0 toglie il limite.",
    },
    AEHUB_RUN_MAX_FAILED_TOOL_CALLS: {
        label: "Tool falliti per run",
        help: "La run si ferma dopo questi errori dei tool. 0 toglie il limite.",
    },
    AEHUB_RUN_MAX_FILES_MODIFIED: {
        label: "File modificati per run",
        help: "La run si ferma dopo aver modificato questi file. 0 toglie il limite.",
    },
    AEHUB_APPROVAL_TTL_SECONDS: {
        label: "Durata di un'approvazione (secondi)",
        help: "Un'approvazione non decisa entro questo tempo viene negata. Vale per le nuove richieste.",
    },
    AEHUB_BREAKER_THRESHOLD: {
        label: "Errori prima di saltare un modello",
        help: "Dopo questi errori di fila un modello della catena viene saltato per un po'.",
    },
    AEHUB_BREAKER_COOLDOWN_SECONDS: {
        label: "Pausa di un modello saltato (secondi)",
        help: "Quanto resta saltato un modello che sbaglia prima di riprovarlo.",
    },
    AEHUB_CONTEXT_BUDGET: {
        label: "Budget di contesto (token)",
        help: "Token di una richiesta al modello, divisi tra i livelli di contesto L0–L5.",
    },
    AEHUB_SNAPSHOT_EVERY: {
        label: "Chiamate tra due riassunti",
        help: "Le chiamate più vecchie escono dalla finestra recente e vengono riassunte (10–20).",
    },
};

export function settingText(field: SettingField): { label: string; help: string } {
    return SETTING_TEXT[field.name] ?? { label: field.label, help: field.help };
}

export interface Target {
    provider: ProviderName;
    model: string;
}

export type Chains = Record<RoleName, Target[]>;

export function parseTarget(label: string): Target {
    const at = label.indexOf(":");
    const provider = label.slice(0, at) as ProviderName;
    return {
        provider: PROVIDERS.includes(provider) ? provider : "openai",
        model: at >= 0 ? label.slice(at + 1) : label,
    };
}

export function targetLabel(target: Target): string {
    return `${target.provider}:${target.model.trim()}`;
}

/** The chains of the custom roles as AEHUB_MODEL_ROLES; "" when none is custom. */
export function rolesJson(chains: Chains, custom: Record<RoleName, boolean>): string {
    const entries = ROLES.filter((role) => custom[role]).map((role) => [
        role,
        chains[role].filter((target) => target.model.trim()).map(targetLabel),
    ]);
    return entries.length ? JSON.stringify(Object.fromEntries(entries)) : "";
}

/** Models the Critic shares with another role: the backend refuses them. */
export function criticConflicts(chains: Chains): { role: RoleName; model: string }[] {
    const critic = new Set(chains.critic.map((target) => target.model.trim()).filter(Boolean));
    const shared: { role: RoleName; model: string }[] = [];
    for (const role of IMPLEMENTER_ROLES) {
        for (const target of chains[role]) {
            const model = target.model.trim();
            if (critic.has(model) && !shared.some((entry) => entry.role === role && entry.model === model)) {
                shared.push({ role, model });
            }
        }
    }
    return shared;
}

/** Roles whose custom chain has no model left: the backend refuses them too. */
export function emptyRoles(chains: Chains, custom: Record<RoleName, boolean>): RoleName[] {
    return ROLES.filter((role) => custom[role] && !chains[role].some((target) => target.model.trim()));
}

/** "128k", "1M" context windows. */
export function contextLabel(tokens: number | null): string {
    if (!tokens) {
        return "";
    }
    return tokens >= 1_000_000 ? `${+(tokens / 1_000_000).toFixed(1)}M` : `${Math.round(tokens / 1000)}k`;
}

/** Italian name and use of each key; the backend's English is the fallback. */
export const SECRET_TEXT: Record<string, { label: string; use: string }> = {
    OPENAI_API_KEY: { label: "OpenAI", use: "modelli del provider openai" },
    OPENROUTER_API_KEY: { label: "OpenRouter", use: "modelli del provider openrouter" },
    AEHUB_LOCAL_API_KEY: { label: "Server locale", use: "provider local, se il server la chiede (facoltativa)" },
    AEHUB_MQTT_PASSWORD: { label: "Broker MQTT", use: "dispositivi di casa (facoltativa)" },
    ELEVENLABS_API_KEY: { label: "ElevenLabs", use: "voce nel cloud (facoltativa)" },
};
