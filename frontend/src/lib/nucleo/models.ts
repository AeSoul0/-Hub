/**
 * @file frontend/src/lib/nucleo/models.ts
 * @description Models, keys and limits in the Control Plane (F4): what each
 * role does, the text of every setting in each interface language, and the
 * role chains the role editor turns into AEHUB_MODEL_ROLES.
 *
 * The role of a task is chosen by rules from its text, without a model; each
 * role then runs on its own chain "provider:model", the first entry first,
 * the others as fallbacks. The Critic (the supervisor) reviews every result
 * and must not share a model with any other role: the backend refuses such a
 * routing, and the editor says so before saving.
 */

import type { ProviderName, RoleName, SettingField, SettingSource } from "@/lib/api/settings";
import { catalog, type Lang } from "@/lib/i18n";

export const ROLES: RoleName[] = ["architect", "research", "critic", "fast_worker", "triage"];
export const IMPLEMENTER_ROLES: RoleName[] = ["architect", "research", "fast_worker", "triage"];
export const PROVIDERS: ProviderName[] = [
    "openai",
    "openrouter",
    "local",
    "groq",
    "anthropic",
    "google",
];
/** Always offered in the role editor. */
export const BASE_PROVIDERS: ProviderName[] = ["openai", "openrouter", "local"];

export const ROLE_INFO = catalog<Record<RoleName, { title: string; job: string }>>({
    en: {
        architect: { title: "Architect", job: "Long tasks: code, design, refactoring, debugging." },
        research: { title: "Research", job: "Research, analysis and comparisons." },
        critic: {
            title: "Critic · supervisor",
            job: "Checks the result of every run and has it redone when it is not right. Uses a model different from every other role.",
        },
        fast_worker: { title: "Fast Worker", job: "Repetitive work: tests, documents, conversions, extraction." },
        triage: { title: "Triage", job: "Short, simple requests: the cheapest models go here." },
    },
    it: {
        architect: { title: "Architect", job: "Compiti lunghi: codice, progettazione, refactoring, debug." },
        research: { title: "Research", job: "Ricerche, analisi e confronti." },
        critic: {
            title: "Critic · supervisore",
            job: "Controlla il risultato di ogni run e lo fa rifare se non va. Usa un modello diverso da tutti gli altri ruoli.",
        },
        fast_worker: { title: "Fast Worker", job: "Lavori ripetitivi: test, documenti, conversioni, estrazioni." },
        triage: { title: "Triage", job: "Richieste brevi e semplici: qui vanno i modelli più economici." },
    },
});

export const PROVIDER_LABELS = catalog<Record<ProviderName, string>>({
    en: {
        openai: "OpenAI",
        openrouter: "OpenRouter",
        local: "Local server",
        groq: "Groq",
        anthropic: "Anthropic",
        google: "Google Gemini",
    },
    it: {
        openai: "OpenAI",
        openrouter: "OpenRouter",
        local: "Server locale",
        groq: "Groq",
        anthropic: "Anthropic",
        google: "Google Gemini",
    },
});

/**
 * The providers the role editor offers (P1, ADR-032): the base ones always,
 * a newer one (Groq, Anthropic, Gemini) once its key is set, or when a saved
 * chain already uses it, so an existing routing never disappears.
 */
export function offeredProviders(
    providers: Partial<Record<ProviderName, { key: boolean }>>,
    used: ProviderName[] = []
): ProviderName[] {
    return PROVIDERS.filter(
        (provider) =>
            BASE_PROVIDERS.includes(provider) || providers[provider]?.key || used.includes(provider)
    );
}

export const SOURCE_LABELS = catalog<Record<SettingSource, string>>({
    en: { database: "set here", environment: "from backend/.env", default: "default" },
    it: { database: "impostato qui", environment: "da backend/.env", default: "predefinito" },
});

type SettingText = Record<string, { label: string; help: string }>;

/** Label and help of each setting; the backend's text is the fallback. */
export const SETTING_TEXT = catalog<SettingText>({
    en: {
        OPENAI_MODEL: { label: "Default model", help: "OpenAI model of the roles without a chain of their own." },
        AEHUB_CHECKER_MODEL: {
            label: "Default Critic",
            help: "Model that checks the result when the Critic has no chain of its own. It must differ from the others.",
        },
        AEHUB_MODEL_ROLES: {
            label: "Role chains (JSON)",
            help: 'Role → list of "provider:model", tried in order. The role editor writes it.',
        },
        AEHUB_FORCE_ROLE: {
            label: "Forced role",
            help: "Every task uses this role instead of choosing it from the text. Empty: by rules.",
        },
        AEHUB_LOCAL_BASE_URL: {
            label: "Local server",
            help: "Address of the OpenAI-compatible server of the local provider (Ollama, LM Studio, vLLM).",
        },
        AEHUB_MODEL_PRICES: {
            label: "Prices (JSON)",
            help: 'Model → {"input": USD, "output": USD} per 1M tokens. The price table writes it.',
        },
        AEHUB_DEFAULT_MODEL_PRICE: {
            label: "Price of a model without a price",
            help: "input,output in USD per 1M tokens. High on purpose: without a price the spend is overestimated.",
        },
        AEHUB_RUN_MAX_COST: {
            label: "Maximum cost of a run (USD)",
            help: "The run stops when it reaches this cost. 0 removes the limit.",
        },
        AEHUB_MONTHLY_BUDGET: {
            label: "Monthly budget (USD)",
            help: "Once this is spent in the month, new runs are refused. 0 removes the limit.",
        },
        AEHUB_BUDGET_WARNING_RATIO: {
            label: "Budget warning threshold",
            help: "Share of the monthly budget that triggers the warning (between 0 and 1).",
        },
        AEHUB_RUN_TIMEOUT_SECONDS: {
            label: "Active time of a run (seconds)",
            help: "Waiting for an approval does not count. 0 removes the limit.",
        },
        AEHUB_RUN_MAX_FAILED_TOOL_CALLS: {
            label: "Failed tools per run",
            help: "The run stops after this many tool errors. 0 removes the limit.",
        },
        AEHUB_RUN_MAX_FILES_MODIFIED: {
            label: "Files modified per run",
            help: "The run stops after modifying this many files. 0 removes the limit.",
        },
        AEHUB_RUN_MAX_SUBAGENTS: {
            label: "Subagents per run",
            help: "How many subagents a run can start with delegate_task. Their cost counts for the run. 0 turns delegation off.",
        },
        AEHUB_APPROVAL_TTL_SECONDS: {
            label: "Lifetime of an approval (seconds)",
            help: "An approval not decided within this time is denied. Applies to new requests.",
        },
        AEHUB_BREAKER_THRESHOLD: {
            label: "Errors before skipping a model",
            help: "After this many errors in a row a model of the chain is skipped for a while.",
        },
        AEHUB_BREAKER_COOLDOWN_SECONDS: {
            label: "Pause of a skipped model (seconds)",
            help: "How long a failing model stays skipped before it is tried again.",
        },
        AEHUB_CONTEXT_BUDGET: {
            label: "Context budget (tokens)",
            help: "Tokens of one request to the model, split among the context levels L0–L5.",
        },
        AEHUB_SNAPSHOT_EVERY: {
            label: "Calls between two summaries",
            help: "The oldest calls leave the recent window and are summarized (10–20).",
        },
        AEHUB_INSTANT_COMMANDS: {
            label: "Instant commands",
            help: "Simple commands (open an app or a folder, a light on or off, lock a door) run at once, without the model. Anything else goes to the engine.",
        },
        AEHUB_APPS: {
            label: "Apps ÆHub may open",
            help: 'JSON: the name you say → the program, e.g. {"spotify": "spotify", "code": ["code", "--new-window"]}. Only these can be opened, and only when ÆHub runs on this computer (not in Docker).',
        },
    },
    it: {
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
        AEHUB_RUN_MAX_SUBAGENTS: {
            label: "Sub-agenti per run",
            help: "Quanti sub-agenti una run può avviare con delegate_task. Il loro costo conta per la run. 0 spegne la delega.",
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
        AEHUB_INSTANT_COMMANDS: {
            label: "Comandi istantanei",
            help: "I comandi semplici (aprire un'app o una cartella, accendere o spegnere una luce, chiudere a chiave una porta) partono subito, senza il modello. Tutto il resto va al motore.",
        },
        AEHUB_APPS: {
            label: "App che ÆHub può aprire",
            help: 'JSON: il nome che dici → il programma, ad esempio {"spotify": "spotify", "code": ["code", "--new-window"]}. Si aprono solo queste, e solo quando ÆHub gira su questo computer (non in Docker).',
        },
    },
});

export function settingText(field: SettingField, lang: Lang): { label: string; help: string } {
    return SETTING_TEXT[lang][field.name] ?? { label: field.label, help: field.help };
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
            if (
                critic.has(model) &&
                !shared.some((entry) => entry.role === role && entry.model === model)
            ) {
                shared.push({ role, model });
            }
        }
    }
    return shared;
}

/** Roles whose custom chain has no model left: the backend refuses them too. */
export function emptyRoles(chains: Chains, custom: Record<RoleName, boolean>): RoleName[] {
    return ROLES.filter(
        (role) => custom[role] && !chains[role].some((target) => target.model.trim())
    );
}

/** "128k", "1M" context windows. */
export function contextLabel(tokens: number | null): string {
    if (!tokens) {
        return "";
    }
    return tokens >= 1_000_000
        ? `${+(tokens / 1_000_000).toFixed(1)}M`
        : `${Math.round(tokens / 1000)}k`;
}

/** Name and use of each key; the backend's text is the fallback. */
export const SECRET_TEXT = catalog<Record<string, { label: string; use: string }>>({
    en: {
        OPENAI_API_KEY: { label: "OpenAI", use: "models of the openai provider" },
        OPENROUTER_API_KEY: { label: "OpenRouter", use: "models of the openrouter provider" },
        GROQ_API_KEY: { label: "Groq", use: "models of the groq provider (optional)" },
        ANTHROPIC_API_KEY: { label: "Anthropic", use: "models of the anthropic provider (optional)" },
        GEMINI_API_KEY: { label: "Google Gemini", use: "models of the google provider (optional)" },
        AEHUB_LOCAL_API_KEY: { label: "Local server", use: "local provider, if the server asks for one (optional)" },
        AEHUB_MQTT_PASSWORD: { label: "MQTT broker", use: "home devices (optional)" },
        ELEVENLABS_API_KEY: { label: "ElevenLabs", use: "cloud voice (optional)" },
        AEHUB_MCP_TOKENS: { label: "MCP tokens", use: "MCP servers with a login, as host=token,host=token (optional)" },
    },
    it: {
        OPENAI_API_KEY: { label: "OpenAI", use: "modelli del provider openai" },
        OPENROUTER_API_KEY: { label: "OpenRouter", use: "modelli del provider openrouter" },
        GROQ_API_KEY: { label: "Groq", use: "modelli del provider groq (facoltativa)" },
        ANTHROPIC_API_KEY: { label: "Anthropic", use: "modelli del provider anthropic (facoltativa)" },
        GEMINI_API_KEY: { label: "Google Gemini", use: "modelli del provider google (facoltativa)" },
        AEHUB_LOCAL_API_KEY: { label: "Server locale", use: "provider local, se il server la chiede (facoltativa)" },
        AEHUB_MQTT_PASSWORD: { label: "Broker MQTT", use: "dispositivi di casa (facoltativa)" },
        ELEVENLABS_API_KEY: { label: "ElevenLabs", use: "voce nel cloud (facoltativa)" },
        AEHUB_MCP_TOKENS: { label: "Token MCP", use: "server MCP con login, come host=token,host=token (facoltativa)" },
    },
});

type IssueParams = Record<string, string>;

const SETUP = "Aggiungila con python scripts/aehub.py setup, poi riavvia con python scripts/aehub.py up.";

/** Each configuration issue in Italian, from its code and values; unknown codes keep the backend text. */
const ISSUE_TEXT: Partial<Record<string, (p: IssueParams) => string>> = {
    routing_invalid: (p) => `I modelli per ruolo non sono validi: ${p.error}`,
    provider_key_missing: (p) => `Il provider ${p.provider} serve a ${p.roles}, ma manca la chiave ${p.key}. ${SETUP}`,
    price_missing: (p) =>
        `Manca il prezzo di ${p.models}: il costo si stima con quello di un modello non in elenco (${p.price} USD per 1M token), quindi spesa e budget sono approssimati.`,
    run_cost_above_budget: (p) =>
        `Una run può costare fino a ${p.run_cost} USD, più del budget mensile di ${p.monthly} USD.`,
    workspace_missing: (p) =>
        `La cartella di lavoro ${p.folder} non esiste: i tool sui file non funzioneranno. Si sceglie con python scripts/aehub.py setup.`,
    workspace_read_only: (p) => `Nella cartella di lavoro ${p.folder} non si può scrivere.`,
    voice_disabled: (p) =>
        p.packages
            ? `La voce ha bisogno di ${p.packages}: installa i requisiti del backend.`
            : "La voce è spenta (AEHUB_VOICE=off).",
    voice_cloud_key_missing: () =>
        "È scelta la voce di ElevenLabs, ma manca la chiave ELEVENLABS_API_KEY: le risposte le legge Piper.",
    voice_cloud_voice_missing: () =>
        "È scelta la voce di ElevenLabs, ma non è selezionata nessuna voce: le risposte le legge Piper.",
    home_devices_invalid: (p) => `I dispositivi di casa sono spenti: ${p.error}`,
    home_broker_missing: (p) => `${p.devices} dispositivi di casa dichiarati, ma: ${p.error}`,
};

/** A configuration issue in the interface language; English is the backend's own text. */
export function issueText(issue: { code: string; message: string; params?: IssueParams }, lang: Lang = "it"): string {
    if (lang === "en") {
        return issue.message;
    }
    const text = ISSUE_TEXT[issue.code];
    return text && issue.params !== undefined ? text(issue.params) : issue.message;
}
