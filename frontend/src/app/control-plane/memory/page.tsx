/**
 * @file frontend/src/app/control-plane/memory/page.tsx
 * @description Long-term memory of the user (roadmap M6, page in M11).
 *
 * GET /api/memory lists what the assistant remembers in this workspace;
 * POST /api/memory/preferences adds a preference written by the user (trusted,
 * injected in every later run); DELETE /api/memory/{id} forgets one memory.
 * Untrusted memories come from tool output: they are recalled as data,
 * never as instructions, and are the first candidates for deletion.
 */
"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

import MemoryList, { type Memory, type TrustFilter } from "@/components/control-plane/MemoryList";
import { deleteJson, getJson, postJson } from "@/lib/api/client";

const KINDS = ["", "preference", "rule", "fact", "episode"] as const;

export default function MemoryPage() {
    const [memories, setMemories] = useState<Memory[]>([]);
    const [kind, setKind] = useState<(typeof KINDS)[number]>("");
    const [trust, setTrust] = useState<TrustFilter>("all");
    const [draft, setDraft] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const refresh = useCallback(async () => {
        try {
            const body = await getJson<{ memories: Memory[] }>("/api/memory", {
                params: kind ? { kind, limit: 500 } : { limit: 500 },
            });
            setMemories(body.memories);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        }
    }, [kind]);

    useEffect(() => {
        const first = setTimeout(refresh, 0);
        return () => clearTimeout(first);
    }, [refresh]);

    const visible = useMemo(
        () =>
            memories.filter(
                (memory) => trust === "all" || (trust === "trusted" ? memory.trusted : !memory.trusted),
            ),
        [memories, trust],
    );

    const addPreference = async (event: React.FormEvent) => {
        event.preventDefault();
        setBusy(true);
        try {
            await postJson("/api/memory/preferences", { content: draft });
            setDraft("");
            await refresh();
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setBusy(false);
        }
    };

    const forget = async (memory: Memory) => {
        if (!window.confirm(`Forget this ${memory.kind}?\n\n${memory.content.slice(0, 200)}`)) {
            return;
        }
        try {
            await deleteJson(`/api/memory/${encodeURIComponent(memory.id)}`);
            setMemories((current) => current.filter((item) => item.id !== memory.id));
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        }
    };

    return (
        <div className="p-8">
            <h1 className="text-3xl font-bold mb-6 text-orange-500">Memory</h1>

            {error && <p className="mb-4 text-red-400">{error}</p>}

            <form onSubmit={addPreference} className="mb-8 flex flex-col gap-2 max-w-2xl">
                <label htmlFor="preference" className="text-sm text-gray-300">
                    Add a preference (used in every later run)
                </label>
                <textarea
                    id="preference"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    maxLength={2000}
                    rows={2}
                    className="rounded bg-gray-900 border border-gray-700 px-3 py-2"
                    placeholder="e.g. Answer in Italian; keep summaries under five lines."
                />
                <button
                    type="submit"
                    disabled={busy || draft.trim().length === 0}
                    className="self-start bg-orange-600 hover:bg-orange-500 disabled:opacity-50 rounded px-4 py-1"
                >
                    Save preference
                </button>
            </form>

            <div className="flex flex-wrap gap-4 mb-4 text-sm">
                <label className="flex items-center gap-2">
                    Kind
                    <select
                        value={kind}
                        onChange={(event) => setKind(event.target.value as (typeof KINDS)[number])}
                        className="bg-gray-900 border border-gray-700 rounded px-2 py-1"
                    >
                        {KINDS.map((item) => (
                            <option key={item} value={item}>
                                {item || "all"}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="flex items-center gap-2">
                    Source
                    <select
                        value={trust}
                        onChange={(event) => setTrust(event.target.value as TrustFilter)}
                        className="bg-gray-900 border border-gray-700 rounded px-2 py-1"
                    >
                        <option value="all">all</option>
                        <option value="trusted">trusted (from you)</option>
                        <option value="untrusted">untrusted (from tools)</option>
                    </select>
                </label>
            </div>

            <MemoryList memories={visible} onForget={forget} />
        </div>
    );
}
