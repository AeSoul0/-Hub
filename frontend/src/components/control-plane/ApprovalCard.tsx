/**
 * @file frontend/src/components/control-plane/ApprovalCard.tsx
 * @description One pending approval: the exact call, its arguments, the
 * time left, and the two decisions.
 */
import Link from "next/link";
import React from "react";

import { runHref } from "@/lib/routes";

export interface ApprovalRequest {
    id: string;
    run_id: string | null;
    session_id: string;
    tool: string;
    risk: string;
    arguments_hash: string;
    arguments?: Record<string, unknown> | null;
    requested_by: string;
    requested_at: string;
    expires_at: string;
}

export type Decision = "allow" | "deny";

// Backend timestamps are naive UTC.
export function secondsLeft(expiresAt: string, now: number): number {
    const expires = Date.parse(expiresAt.endsWith("Z") ? expiresAt : `${expiresAt}Z`);
    return Math.max(0, Math.round((expires - now) / 1000));
}

export default function ApprovalCard({
    item,
    now,
    busy,
    onDecide,
}: {
    item: ApprovalRequest;
    now: number;
    busy: boolean;
    onDecide: (id: string, decision: Decision) => void;
}) {
    const remaining = secondsLeft(item.expires_at, now);
    const disabled = busy || remaining === 0;

    return (
        <article className="border border-gray-800 rounded p-4" aria-label={`Approval for ${item.tool}`}>
            <header className="flex flex-wrap items-center gap-3 mb-3">
                <span className="font-mono text-lg">{item.tool}</span>
                <span className="text-yellow-500 uppercase text-sm">{item.risk}</span>
                <span className="text-gray-400 text-sm">
                    {remaining > 0 ? `expires in ${remaining}s` : "expired"}
                </span>
                {item.run_id && (
                    <Link
                        href={runHref(item.run_id)}
                        className="text-cyan-400 hover:underline text-sm font-mono"
                    >
                        run {item.run_id}
                    </Link>
                )}
            </header>

            {item.arguments ? (
                <pre className="bg-black/40 rounded p-3 text-sm overflow-x-auto mb-3">
                    {JSON.stringify(item.arguments, null, 2)}
                </pre>
            ) : (
                <p className="text-gray-400 text-sm mb-3">
                    Arguments not available (hash {item.arguments_hash.slice(0, 12)}…): open the run before
                    allowing.
                </p>
            )}

            <div className="flex gap-2">
                <button
                    onClick={() => onDecide(item.id, "allow")}
                    disabled={disabled}
                    className="bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white px-4 py-1 rounded"
                >
                    Allow once
                </button>
                <button
                    onClick={() => onDecide(item.id, "deny")}
                    disabled={disabled}
                    className="bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white px-4 py-1 rounded"
                >
                    Deny
                </button>
            </div>
        </article>
    );
}
