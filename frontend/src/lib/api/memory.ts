/**
 * @file frontend/src/lib/api/memory.ts
 * @description Memory and documents (F6, ADR-027): types of /api/memory and
 * /api/documents, the citations an answer carries, and the memory settings
 * the MEMORIA and DOCUMENTI pages write through PUT /api/settings.
 */

export type MemoryKind = "fact" | "preference" | "rule" | "episode";
export type TrustFilter = "all" | "trusted" | "untrusted";

export interface Memory {
    id: string;
    kind: MemoryKind | string;
    content: string;
    /** False when written while a run held untrusted content (web, files, MCP). */
    trusted: boolean;
    session_id: string | null;
    created_at: string | null;
    score: number | null;
    /** "user", "user-edit", "agent", … */
    source?: string | null;
}

export interface MemoryStatus {
    enabled: boolean;
    /** The configured embedder ("hash-v1", "st:all-MiniLM-L6-v2"); null when invalid. */
    embedder: string | null;
    embedder_kind: string;
    min_similarity: number;
    total: number;
    by_kind: Record<string, number>;
    untrusted: number;
    /** Memories whose vector came from another embedder, or has none. */
    stale_vectors: number;
}

export interface MemoryView {
    memories: Memory[];
    status: MemoryStatus;
}

export interface MemoryChanges {
    content?: string;
    kind?: MemoryKind;
    trusted?: boolean;
}

export interface DocumentFileInfo {
    path: string;
    size: number;
    chunks: number;
    error: string | null;
    indexed_at: string | null;
}

export interface DocumentsView {
    root: string;
    root_exists: boolean;
    files: DocumentFileInfo[];
    max_file_mb: number;
    suffixes: string[];
    totals: { files: number; chunks: number; errors: number };
    stale_vectors: number;
}

export interface SyncReport {
    root: string;
    root_exists: boolean;
    added: string[];
    updated: string[];
    removed: string[];
    failed: { path: string; error: string }[];
    unchanged: number;
    pending: number;
    truncated: boolean;
}

export interface DocumentHit {
    path: string;
    locator: string;
    citation: string;
    content: string;
    score: number;
}

export interface Passage {
    path: string;
    locator: string;
    content: string;
}

/** AEHUB_MEMORY_ENABLED as the backend reads it: off only for 0/false/off/no. */
export function memoryOn(value: string | undefined): boolean {
    return !["0", "false", "off", "no"].includes((value ?? "on").trim().toLowerCase());
}

export type CitedPart = string | { citation: string; path: string; locator: string };

/** Split an answer into text and its citations [doc: path#L12-30] / [doc: path#p3]. */
export function splitCitations(text: string): CitedPart[] {
    const parts: CitedPart[] = [];
    const pattern = /\[doc:\s*([^\]#\n]+?)\s*#\s*(L\d+-\d+|p\d+)\s*\]/g;
    let last = 0;

    for (const match of text.matchAll(pattern)) {
        const at = match.index ?? 0;
        if (at > last) {
            parts.push(text.slice(last, at));
        }
        parts.push({ citation: match[0], path: match[1].trim(), locator: match[2] });
        last = at + match[0].length;
    }

    if (last < text.length) {
        parts.push(text.slice(last));
    }
    return parts;
}

/** "L12-30" → "righe 12-30", "p3" → "pagina 3". */
export function locatorLabel(locator: string): string {
    if (locator.startsWith("p")) {
        return `pagina ${locator.slice(1)}`;
    }
    return `righe ${locator.slice(1)}`;
}

export function formatSize(bytes: number): string {
    if (bytes < 1024) {
        return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
