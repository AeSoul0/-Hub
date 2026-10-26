/**
 * @file frontend/src/lib/nucleo/tools.ts
 * @description Italian text of the Strumenti, Skill and Sicurezza pages
 * (F5): risks, the built-in skills and tools, the warnings of an imported
 * SKILL.md, and the decisions of the audit. The backend's English is the
 * fallback for anything not listed.
 */

import type { Risk, SkillSource, SkillWarning } from "@/lib/api/tools";

export const RISK_LABELS: Record<Risk, { label: string; tone: "ok" | "warn" | "bad" }> = {
    low: { label: "rischio basso", tone: "ok" },
    medium: { label: "rischio medio", tone: "warn" },
    high: { label: "rischio alto", tone: "bad" },
};

export const SOURCE_TEXT: Record<SkillSource, string> = {
    builtin: "integrata",
    imported: "importate",
    mcp: "server MCP",
};

export const SKILL_TEXT: Record<string, { title: string; description: string }> = {
    browser_automation: { title: "Browser", description: "Apre una pagina web e ne legge il testo." },
    documents: { title: "Documenti", description: "Cerca nei documenti della cartella di lavoro e cita la fonte." },
    home: {
        title: "Casa",
        description: "Comanda i dispositivi dichiarati (luci, serrature) via MQTT. Senza dispositivi non ha tool.",
    },
    memory: { title: "Memoria", description: "Salva fatti, procedure e preferenze da ricordare nelle sessioni dopo." },
    sandbox: { title: "Sandbox", description: "Esegue Python e comandi shell in un container isolato, senza rete." },
    web_search: { title: "Ricerca web", description: "Cerca sul web informazioni aggiornate." },
    imported_skills: {
        title: "Skill importate",
        description:
            "Le skill SKILL.md accese, lette dall'agente con use_skill. Il tool c'è solo quando almeno una skill è accesa.",
    },
};

export const TOOL_TEXT: Record<string, string> = {
    browse_and_extract: "Apre un indirizzo controllato e ne estrae il testo visibile.",
    search_documents: "Cerca nei documenti (testo, Markdown, PDF) della cartella di lavoro.",
    save_semantic_memory: "Salva un fatto da ricordare.",
    save_procedural_memory: "Salva una procedura da ricordare.",
    save_user_preference: "Salva una tua preferenza.",
    execute_python_code: "Esegue codice Python nella sandbox.",
    execute_shell_script: "Esegue un comando shell nella sandbox.",
    perform_web_search: "Cerca sul web con DuckDuckGo.",
    use_skill: "Legge le istruzioni di una skill importata e accesa.",
};

export const WARNING_TEXT: Record<SkillWarning, string> = {
    download_and_run: "Scarica qualcosa da internet e lo esegue subito (per esempio curl … | bash).",
    encoded_payload: "Contiene un lungo blocco codificato (base64 o simile): può nascondere istruzioni.",
    instruction_override: "Prova a far ignorare le istruzioni precedenti o parla del prompt di sistema.",
    secrets: "Parla di password, chiavi, file .env o chiavi SSH.",
    bundled_files: "Cita file della skill (scripts/, references/, assets/) che non vengono importati.",
    external_links: "Contiene link esterni.",
};

/** Decisions the Tool Gateway records, and the Control Plane changes. */
export const DECISION_TEXT: Record<string, { label: string; tone?: "ok" | "warn" | "bad" | "live" }> = {
    ALLOW: { label: "consentito", tone: "ok" },
    DENY: { label: "rifiutato", tone: "bad" },
    EXECUTING: { label: "in esecuzione", tone: "live" },
    CACHED: { label: "dalla cache" },
    ERROR: { label: "errore", tone: "bad" },
    CANCELLED: { label: "annullato", tone: "warn" },
};

export const ACTION_TEXT: Record<string, string> = {
    "settings.update": "impostazioni cambiate",
    "skill.import": "skill importata",
    "skill.enable": "skill accesa",
    "skill.disable": "skill spenta",
    "skill.delete": "skill eliminata",
};

export function skillTitle(name: string): string {
    return SKILL_TEXT[name]?.title ?? name;
}

/** "file:SKILL.md" → "file SKILL.md"; a link stays as it is. */
export function sourceLabel(source: string): string {
    return source.startsWith("file:") ? `file ${source.slice(5)}` : source;
}

/** Italian text of the import errors the backend returns (English). */
const IMPORT_ERRORS: [RegExp, string | ((match: RegExpMatchArray) => string)][] = [
    [/^Use an https link/, "Serve un link https."],
    [/^Links with credentials/, "Il link non può contenere credenziali."],
    [/^Link a SKILL\.md file or a skill folder/, "Su GitHub indica un file SKILL.md o la cartella di una skill."],
    [/not public/, "Il link punta a un indirizzo non pubblico: non viene scaricato."],
    [/redirects to an address that is not https/, "Il link rimanda a un indirizzo non https."],
    [/too large/, "Il file è troppo grande per una SKILL.md."],
    [/not UTF-8 text/, "Il file non è testo UTF-8."],
    [/^Too many redirects/, "Troppi rimandi."],
    [/^The link answered (\d+)/, (match) => `Il link ha risposto ${match[1]}.`],
    [/starts with a front matter block/, "Una SKILL.md comincia con un blocco tra due righe ---, con name e description."],
    [/not closed by a --- line/, "Il blocco iniziale non è chiuso da una riga ---."],
    [/has no name/, "Manca il campo name."],
    [/has no description/, "Manca il campo description."],
    [/no instructions after the front matter/, "Dopo il blocco iniziale non ci sono istruzioni."],
    [/^The description can be at most (\d+)/, (match) => `La descrizione può avere al massimo ${match[1]} caratteri.`],
    [/^A SKILL\.md can be at most (\d+)/, (match) => `Una SKILL.md può avere al massimo ${match[1]} caratteri.`],
    [/^The file is not text/, "Il file non è testo."],
    [/^Send either a link or the text/, "Manda un link oppure un file."],
    [/^Only an admin/, "Solo un amministratore può cambiare le skill."],
];

export function importErrorText(message: string): string {
    for (const [pattern, text] of IMPORT_ERRORS) {
        const match = message.match(pattern);
        if (match) {
            return typeof text === "string" ? text : text(match);
        }
    }
    return message;
}
