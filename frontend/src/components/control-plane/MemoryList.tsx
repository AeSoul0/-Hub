/**
 * @file frontend/src/components/control-plane/MemoryList.tsx
 * @description The memories of the user, with their source and a way to
 * forget each one.
 */
import React from "react";

import { TrustBadge } from "@/components/control-plane/RunDetailView";

export interface Memory {
    id: string;
    kind: string;
    content: string;
    trusted: boolean;
    session_id: string | null;
    created_at: string | null;
    score: number | null;
}

export type TrustFilter = "all" | "trusted" | "untrusted";

export default function MemoryList({
    memories,
    onForget,
}: {
    memories: Memory[];
    onForget: (memory: Memory) => void;
}) {
    if (memories.length === 0) {
        return <p className="text-gray-400">Nothing remembered here.</p>;
    }

    return (
        <ul className="space-y-2">
            {memories.map((memory) => (
                <li key={memory.id} className="border border-gray-800 rounded p-3 flex gap-4 items-start">
                    <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-1 text-xs">
                            <span className="uppercase text-gray-400">{memory.kind}</span>
                            <TrustBadge trusted={memory.trusted} />
                            <span className="text-gray-500">{memory.created_at ?? ""}</span>
                        </div>
                        <p className="whitespace-pre-wrap break-words">{memory.content}</p>
                    </div>
                    <button
                        onClick={() => onForget(memory)}
                        className="text-sm text-red-400 hover:text-red-300"
                        aria-label={`Forget ${memory.kind} ${memory.id}`}
                    >
                        Forget
                    </button>
                </li>
            ))}
        </ul>
    );
}
