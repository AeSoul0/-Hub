/**
 * @file frontend/src/lib/api/tools.ts
 * @description Tools, skills and their boundaries (F5, ADR-026): types of
 * GET /api/tools and /api/skills, and the setting values the Strumenti page
 * writes through PUT /api/settings.
 *
 * Switching a tool off is the setting AEHUB_DISABLED_TOOLS: the engine
 * neither shows it to the model nor runs it. Imported SKILL.md skills start
 * off; the agent reads an enabled one through the use_skill tool, as
 * untrusted content.
 */

export type Risk = "low" | "medium" | "high";
export type SkillSource = "builtin" | "imported" | "mcp";

export interface ToolInfo {
    name: string;
    description: string;
    risk: Risk;
    requires_approval: boolean;
    network: boolean;
    filesystem: boolean;
    modifies_files: boolean;
    /** The output is third-party content (web, files, MCP, imported skills). */
    untrusted_output: boolean;
    enabled: boolean;
}

export interface SkillGroup {
    name: string;
    description: string;
    version: string;
    source: SkillSource;
    tools: ToolInfo[];
}

export interface ToolsView {
    skills: SkillGroup[];
    /** Every name in AEHUB_DISABLED_TOOLS, also of tools no longer registered. */
    disabled: string[];
    selection: { enabled: boolean; top_k: number; tools: number; active: boolean };
    boundaries: {
        directories: { path: string; exists: boolean }[];
        api_hosts: string[];
        mcp_servers: string[];
    };
    sandbox: { docker: boolean; image: string; memory_limit: string; network: boolean };
    sources: Record<string, "database" | "environment" | "default">;
}

export type SkillWarning =
    | "download_and_run"
    | "encoded_payload"
    | "instruction_override"
    | "secrets"
    | "bundled_files"
    | "external_links";

export interface ImportedSkill {
    id: string;
    name: string;
    description: string;
    /** The https link it came from, or "file:<name>". */
    source: string;
    sha256: string;
    warnings: SkillWarning[];
    enabled: boolean;
    chars: number;
    created_at: string | null;
    updated_at: string | null;
}

export interface ImportedSkillDetail extends ImportedSkill {
    content: string;
    /** Only on import: a skill with the same name was replaced. */
    replaced?: boolean;
    /** Only on import: false when the very same text was imported again. */
    changed?: boolean;
}

/** AEHUB_DISABLED_TOOLS after switching one tool on or off. */
export function disabledValue(disabled: string[], tool: string, enabled: boolean): string | null {
    const next = new Set(disabled);
    if (enabled) {
        next.delete(tool);
    } else {
        next.add(tool);
    }
    return next.size ? [...next].sort().join(",") : null;
}

/** AEHUB_MCP_ALLOWED_SERVERS from the edited rows: trimmed, blank rows dropped. */
export function serversValue(rows: string[]): string | null {
    const servers = rows.map((row) => row.trim()).filter(Boolean);
    return servers.length ? servers.join(",") : null;
}

/** A server URL the backend will accept: http(s), a host, no credentials or spaces. */
export function validServer(url: string): boolean {
    return /^https?:\/\/[^\s,@/]+(\/[^\s,@]*)?$/.test(url.trim());
}
