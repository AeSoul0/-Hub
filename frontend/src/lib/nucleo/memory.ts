/**
 * @file frontend/src/lib/nucleo/memory.ts
 * @description Text of the Memory and Documents pages (F6) in each interface
 * language: kinds and sources of a memory, the embedders, and the backend's
 * errors.
 */

import type { MemoryKind } from "@/lib/api/memory";
import { catalog, type Lang } from "@/lib/i18n";

export const KIND_TEXT = catalog<Record<MemoryKind, { label: string; help: string }>>({
    en: {
        fact: { label: "fact", help: "Recalled when the task resembles it." },
        preference: { label: "preference", help: "Goes into every run, if it is trusted." },
        rule: { label: "rule", help: "Goes into every run, if it is trusted." },
        episode: { label: "episode", help: "The summary of an accepted run." },
    },
    it: {
        fact: { label: "fatto", help: "Si ricorda quando il compito gli somiglia." },
        preference: { label: "preferenza", help: "Entra in ogni run, se è affidabile." },
        rule: { label: "regola", help: "Entra in ogni run, se è affidabile." },
        episode: { label: "episodio", help: "Il riassunto di una run accettata." },
    },
});

export const USER_KINDS: MemoryKind[] = ["fact", "preference", "rule"];

export function kindLabel(kind: string, lang: Lang = "en"): string {
    return KIND_TEXT[lang][kind as MemoryKind]?.label ?? kind;
}

const SOURCES = catalog<Record<string, string>>({
    en: { user: "written by you", "user-edit": "edited by you", agent: "saved by the agent" },
    it: { user: "scritto da te", "user-edit": "modificato da te", agent: "salvato dall'agente" },
});

export function sourceText(source: string | null | undefined, lang: Lang = "en"): string {
    return (source && SOURCES[lang][source]) || (source ?? "");
}

export const EMBEDDERS = catalog<Record<string, { label: string; help: string }>>({
    en: {
        "sentence-transformers": {
            label: "Local model",
            help: "Finds memories by meaning. The model (~90 MB) is downloaded the first time, checked, and runs on this computer. Another model is named with its commit: owner/name@commit.",
        },
        hash: { label: "Hash, without a model", help: "No download, but it finds almost only the same words." },
    },
    it: {
        "sentence-transformers": {
            label: "Modello locale",
            help: "Trova i ricordi per significato. Il modello (~90 MB) si scarica al primo uso, viene controllato e gira su questo computer. Un altro modello si indica con il suo commit: owner/nome@commit.",
        },
        hash: { label: "Hash, senza modello", help: "Niente download, ma trova quasi solo le parole uguali." },
    },
});

/** Italian text of the memory and documents errors the backend returns (in English). */
const ERRORS: [RegExp, string | ((match: RegExpMatchArray) => string)][] = [
    [/must not contain credentials or secrets/, "Un ricordo non può contenere password, chiavi o token."],
    [/already exists/, "Lo stesso ricordo c'è già."],
    [/can be at most (\d+) characters/, (match) => `Un ricordo può avere al massimo ${match[1]} caratteri.`],
    [/cannot be empty/, "Un ricordo non può essere vuoto."],
    [/No memory with this id/, "Questo ricordo non c'è più."],
    [/embedder is not available/, "Il modello degli embedding non è disponibile: controlla le impostazioni."],
    [/Use a plain file name/, "Usa un nome di file semplice, senza cartelle né caratteri speciali."],
    [/Only \.txt, \.md, \.markdown and \.pdf/, "Si indicizzano solo file .txt, .md, .markdown e .pdf."],
    [/larger than the document size limit/, "Il file supera la dimensione massima dei documenti."],
    [/already in the working folder/, "C'è già un file con questo nome: spunta \"sostituisci\" per rimpiazzarlo."],
    [/working folder does not exist/, "La cartella di lavoro non esiste."],
    [/needs file access/, "Serve il permesso di accesso ai file."],
    [/Only an admin/, "Solo un amministratore può aggiungere file."],
    [/not in the document index/, "Questa citazione non è nell'indice dei documenti."],
];

const GUARDRAIL = catalog({
    en: "The text looks like an attempt to change the agent's instructions: it is not saved.",
    it: "Il testo sembra un tentativo di cambiare le istruzioni dell'agente: non viene salvato.",
});

/** A memory or documents error in the interface language; English is the backend's own text. */
export function errorText(message: string, lang: Lang = "en"): string {
    // Guardrail refusals ("Input rejected: ...") get a plain sentence in any language.
    const refused = /Input rejected|jailbreak|injection/i.test(message);
    if (lang === "en") {
        return refused ? GUARDRAIL.en : message;
    }
    for (const [pattern, text] of ERRORS) {
        const match = message.match(pattern);
        if (match) {
            return typeof text === "string" ? text : text(match);
        }
    }
    return refused ? GUARDRAIL.it : message;
}
