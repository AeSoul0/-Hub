/**
 * @file frontend/src/lib/nucleo/tools.ts
 * @description Text of the Tools, Skills and Security pages (F5), in every
 * interface language: risks, the built-in skills and tools, the warnings of
 * an imported SKILL.md, and the decisions of the audit. The backend's text
 * is the fallback for anything not listed.
 */

import type { Risk, SkillSource, SkillWarning } from "@/lib/api/tools";
import { catalog, type Lang } from "@/lib/i18n";

type Tone = "ok" | "warn" | "bad";

const RISK_TONES: Record<Risk, Tone> = { low: "ok", medium: "warn", high: "bad" };

export const RISK_LABELS = catalog<Record<Risk, { label: string; tone: Tone }>>({
    en: {
        low: { label: "low risk", tone: RISK_TONES.low },
        medium: { label: "medium risk", tone: RISK_TONES.medium },
        high: { label: "high risk", tone: RISK_TONES.high },
    },
    it: {
        low: { label: "rischio basso", tone: RISK_TONES.low },
        medium: { label: "rischio medio", tone: RISK_TONES.medium },
        high: { label: "rischio alto", tone: RISK_TONES.high },
    },
});

export const SOURCE_TEXT = catalog<Record<SkillSource, string>>({
    en: { builtin: "built in", imported: "imported", mcp: "MCP servers" },
    it: { builtin: "integrata", imported: "importate", mcp: "server MCP" },
});

export const SKILL_TEXT = catalog<Record<string, { title: string; description: string }>>({
    en: {
        browser_automation: { title: "Browser", description: "Opens a web page and reads its text." },
        documents: {
            title: "Documents",
            description: "Searches the documents of the working folder and cites the source.",
        },
        home: {
            title: "Home",
            description: "Controls the declared devices (lights, locks) over MQTT. Without devices it has no tools.",
        },
        interface: {
            title: "Interface",
            description: "The app itself: Aurora changes its language and the notice about the voice language.",
        },
        memory: { title: "Memory", description: "Saves facts, procedures and preferences for later sessions." },
        sandbox: {
            title: "Sandbox",
            description: "Runs Python and shell commands in an isolated container, without network.",
        },
        web_search: { title: "Web search", description: "Searches the web for current information." },
        mcp: {
            title: "MCP servers",
            description:
                "The tools of the allowed MCP servers. Every call waits for your approval until you lower that tool's risk.",
        },
        imported_skills: {
            title: "Imported skills",
            description:
                "The SKILL.md skills that are on, read by the agent with use_skill. The tool exists only while at least one skill is on.",
        },
    },
    it: {
        browser_automation: { title: "Browser", description: "Apre una pagina web e ne legge il testo." },
        documents: {
            title: "Documenti",
            description: "Cerca nei documenti della cartella di lavoro e cita la fonte.",
        },
        home: {
            title: "Casa",
            description: "Comanda i dispositivi dichiarati (luci, serrature) via MQTT. Senza dispositivi non ha tool.",
        },
        interface: {
            title: "Interfaccia",
            description: "L'app stessa: Aurora ne cambia la lingua e l'avviso sulla lingua della voce.",
        },
        memory: { title: "Memoria", description: "Salva fatti, procedure e preferenze da ricordare nelle sessioni dopo." },
        sandbox: {
            title: "Sandbox",
            description: "Esegue Python e comandi shell in un container isolato, senza rete.",
        },
        web_search: { title: "Ricerca web", description: "Cerca sul web informazioni aggiornate." },
        mcp: {
            title: "Server MCP",
            description:
                "I tool dei server MCP consentiti. Ogni chiamata aspetta la tua approvazione, finché non abbassi il rischio di quel tool.",
        },
        imported_skills: {
            title: "Skill importate",
            description:
                "Le skill SKILL.md accese, lette dall'agente con use_skill. Il tool c'è solo quando almeno una skill è accesa.",
        },
    },
});

export const TOOL_TEXT = catalog<Record<string, string>>({
    en: {
        browse_and_extract: "Opens a checked address and extracts its visible text.",
        search_documents: "Searches the documents (text, Markdown, PDF) of the working folder.",
        save_semantic_memory: "Saves a fact to remember.",
        save_procedural_memory: "Saves a procedure to remember.",
        save_user_preference: "Saves one of your preferences.",
        execute_python_code: "Runs Python code in the sandbox.",
        execute_shell_script: "Runs a shell command in the sandbox.",
        perform_web_search: "Searches the web with DuckDuckGo.",
        use_skill: "Reads the instructions of an imported skill that is on.",
        set_interface_language: "Changes the language of the interface.",
        set_voice_language_warning: "Turns the notice about the voice language on or off.",
    },
    it: {
        browse_and_extract: "Apre un indirizzo controllato e ne estrae il testo visibile.",
        search_documents: "Cerca nei documenti (testo, Markdown, PDF) della cartella di lavoro.",
        save_semantic_memory: "Salva un fatto da ricordare.",
        save_procedural_memory: "Salva una procedura da ricordare.",
        save_user_preference: "Salva una tua preferenza.",
        execute_python_code: "Esegue codice Python nella sandbox.",
        execute_shell_script: "Esegue un comando shell nella sandbox.",
        perform_web_search: "Cerca sul web con DuckDuckGo.",
        use_skill: "Legge le istruzioni di una skill importata e accesa.",
        set_interface_language: "Cambia la lingua dell'interfaccia.",
        set_voice_language_warning: "Accende o spegne l'avviso sulla lingua della voce.",
    },
});

export const WARNING_TEXT = catalog<Record<SkillWarning, string>>({
    en: {
        download_and_run: "Downloads something from the internet and runs it at once (for example curl … | bash).",
        encoded_payload: "Contains a long encoded block (base64 or similar): it can hide instructions.",
        instruction_override: "Tries to make the agent ignore earlier instructions, or talks about the system prompt.",
        secrets: "Talks about passwords, keys, .env files or SSH keys.",
        bundled_files: "Mentions files of the skill (scripts/, references/, assets/) that are not imported.",
        external_links: "Contains external links.",
    },
    it: {
        download_and_run: "Scarica qualcosa da internet e lo esegue subito (per esempio curl … | bash).",
        encoded_payload: "Contiene un lungo blocco codificato (base64 o simile): può nascondere istruzioni.",
        instruction_override: "Prova a far ignorare le istruzioni precedenti o parla del prompt di sistema.",
        secrets: "Parla di password, chiavi, file .env o chiavi SSH.",
        bundled_files: "Cita file della skill (scripts/, references/, assets/) che non vengono importati.",
        external_links: "Contiene link esterni.",
    },
});

type DecisionTone = "ok" | "warn" | "bad" | "live";

/** Decisions the Tool Gateway records, and the Control Plane changes. */
export const DECISION_TEXT = catalog<Record<string, { label: string; tone?: DecisionTone }>>({
    en: {
        ALLOW: { label: "allowed", tone: "ok" },
        DENY: { label: "refused", tone: "bad" },
        EXECUTING: { label: "running", tone: "live" },
        CACHED: { label: "from the cache" },
        ERROR: { label: "error", tone: "bad" },
        CANCELLED: { label: "cancelled", tone: "warn" },
    },
    it: {
        ALLOW: { label: "consentito", tone: "ok" },
        DENY: { label: "rifiutato", tone: "bad" },
        EXECUTING: { label: "in esecuzione", tone: "live" },
        CACHED: { label: "dalla cache" },
        ERROR: { label: "errore", tone: "bad" },
        CANCELLED: { label: "annullato", tone: "warn" },
    },
});

export const ACTION_TEXT = catalog<Record<string, string>>({
    en: {
        "settings.update": "settings changed",
        "skill.import": "skill imported",
        "skill.enable": "skill turned on",
        "skill.disable": "skill turned off",
        "skill.delete": "skill deleted",
    },
    it: {
        "settings.update": "impostazioni cambiate",
        "skill.import": "skill importata",
        "skill.enable": "skill accesa",
        "skill.disable": "skill spenta",
        "skill.delete": "skill eliminata",
    },
});

export function skillTitle(name: string, lang: Lang): string {
    return SKILL_TEXT[lang][name]?.title ?? name;
}

/** "file:SKILL.md" → "file SKILL.md"; a link stays as it is. */
export function sourceLabel(source: string): string {
    return source.startsWith("file:") ? `file ${source.slice(5)}` : source;
}

/** Italian text of the import errors the backend returns (in English). */
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

/** An import error in the interface language; English is the backend's own text. */
export function importErrorText(message: string, lang: Lang = "it"): string {
    if (lang === "en") {
        return message;
    }
    for (const [pattern, text] of IMPORT_ERRORS) {
        const match = message.match(pattern);
        if (match) {
            return typeof text === "string" ? text : text(match);
        }
    }
    return message;
}
