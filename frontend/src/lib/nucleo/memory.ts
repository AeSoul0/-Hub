/**
 * @file frontend/src/lib/nucleo/memory.ts
 * @description Italian text of the MEMORIA and DOCUMENTI pages (F6): kinds
 * and sources of a memory, the embedders, and the backend's errors.
 */

import type { MemoryKind } from "@/lib/api/memory";

export const KIND_TEXT: Record<MemoryKind, { label: string; help: string }> = {
    fact: { label: "fatto", help: "Si ricorda quando il compito gli somiglia." },
    preference: { label: "preferenza", help: "Entra in ogni run, se è affidabile." },
    rule: { label: "regola", help: "Entra in ogni run, se è affidabile." },
    episode: { label: "episodio", help: "Il riassunto di una run accettata." },
};

export const USER_KINDS: MemoryKind[] = ["fact", "preference", "rule"];

export function kindLabel(kind: string): string {
    return KIND_TEXT[kind as MemoryKind]?.label ?? kind;
}

export function sourceText(source: string | null | undefined): string {
    switch (source) {
        case "user":
            return "scritto da te";
        case "user-edit":
            return "modificato da te";
        case "agent":
            return "salvato dall'agente";
        default:
            return source ?? "";
    }
}

export const EMBEDDERS: Record<string, { label: string; help: string }> = {
    "sentence-transformers": {
        label: "Modello locale",
        help: "Trova i ricordi per significato. Il modello (~90 MB) si scarica al primo uso e gira su questo computer.",
    },
    hash: {
        label: "Hash, senza modello",
        help: "Niente download, ma trova quasi solo le parole uguali.",
    },
};

/** Italian text of the memory and documents errors the backend returns (English). */
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

export function errorText(message: string): string {
    for (const [pattern, text] of ERRORS) {
        const match = message.match(pattern);
        if (match) {
            return typeof text === "string" ? text : text(match);
        }
    }
    // Guardrail refusals ("Input rejected: ...") read the same in any language.
    return /Input rejected|jailbreak|injection/i.test(message)
        ? "Il testo sembra un tentativo di cambiare le istruzioni dell'agente: non viene salvato."
        : message;
}
