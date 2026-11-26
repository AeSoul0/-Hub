/**
 * @file frontend/src/components/interface/InterfaceProvider.tsx
 * @description The interface of every page (ADR-034): reads GET
 * /api/interface at start, when the window comes back into focus and on
 * `interface.changed` (IMPOSTAZIONI or Aurora changed the language, the voice
 * or the notice), and shows the notice when the chosen voice speaks another
 * language than the interface.
 *
 * The notice has OK and "Don't show this again". Once dismissed it stays
 * away for this browser session for the same pair of languages; "don't show
 * again" turns AEHUB_VOICE_LANGUAGE_WARNING off, and IMPOSTAZIONI → Language
 * or Aurora turn it back on.
 *
 * The same stream feeds the approval notices (ADR-037): the tab title counts the
 * pending approvals and a system notification calls the owner.
 */
"use client";

import React, { useCallback, useEffect, useState } from "react";

import styles from "@/components/control-plane/control.module.css";
import { APPROVAL_EVENTS, useApprovalNotices } from "@/components/interface/ApprovalNotifier";
import { getJson, putJson } from "@/lib/api/client";
import { useWorkspaceEvents } from "@/lib/api/events";
import {
    LANGUAGE_NAMES,
    applyInterface,
    chooseVoiceWarning,
    registerInterfaceLoader,
    useInterface,
    useText,
    catalog,
    type InterfaceState,
} from "@/lib/i18n";

const DISMISSED_KEY = "aehub.voice-notice-dismissed";

const TEXT = catalog({
    en: {
        title: "The voice speaks another language",
        body: (ui: string, voice: string, name: string) =>
            `The interface is in ${ui}, but the chosen voice (${name}) speaks ${voice}: spoken replies will sound ${voice}.`,
        change: "You can choose another voice on the Voice page.",
        never: "Don't show this again",
        later: "You can turn this notice back on in Settings → Language, or by asking Aurora.",
        ok: "OK",
        failed: "Not saved: ",
    },
    it: {
        title: "La voce parla un'altra lingua",
        body: (ui: string, voice: string, name: string) =>
            `L'interfaccia è in ${ui}, ma la voce scelta (${name}) parla ${voice}: le risposte lette ad alta voce suoneranno in ${voice}.`,
        change: "Puoi scegliere un'altra voce nella pagina Voce.",
        never: "Non mostrare più",
        later: "Puoi riattivare questo avviso da Impostazioni → Lingua, o chiedendolo ad Aurora.",
        ok: "OK",
        failed: "Non salvato: ",
    },
});

function dismissedPair(): string | null {
    try {
        return window.sessionStorage.getItem(DISMISSED_KEY);
    } catch {
        return null;
    }
}

function dismiss(pair: string): void {
    try {
        window.sessionStorage.setItem(DISMISSED_KEY, pair);
    } catch {
        // Storage refused: the notice comes back on the next page load.
    }
}

/** "en:it" when the notice is due, else null. */
export function noticePair(state: InterfaceState | null): string | null {
    if (!state || !state.voice_language_warning || !state.voice.enabled || !state.voice.language) {
        return null;
    }
    return state.voice.language === state.language ? null : `${state.language}:${state.voice.language}`;
}

export function VoiceLanguageNotice() {
    const state = useInterface();
    const t = useText(TEXT);
    const names = useText(LANGUAGE_NAMES);
    const [never, setNever] = useState(false);
    const [closed, setClosed] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const pair = noticePair(state);

    if (!state || !pair || closed === pair || dismissedPair() === pair) {
        return null;
    }

    const voice = state.voice.language ?? "";
    const close = async () => {
        if (never) {
            try {
                await putJson("/api/settings", { values: { AEHUB_VOICE_LANGUAGE_WARNING: "off" } });
                chooseVoiceWarning(false);
            } catch (err) {
                setError(`${t.failed}${err instanceof Error ? err.message : String(err)}`);
                return;
            }
        }
        dismiss(pair);
        setClosed(pair);
    };

    return (
        <div className={styles.backdrop}>
            <div
                className={`${styles.card} ${styles.dialog}`}
                role="dialog"
                aria-modal="true"
                aria-labelledby="voice-notice-title"
            >
                <h2 id="voice-notice-title" className={styles.h2}>
                    {t.title}
                </h2>
                <p>{t.body(names[state.language] ?? state.language, names[voice] ?? voice, state.voice.name)}</p>
                <p className={styles.help}>{t.change}</p>
                <label className={styles.check}>
                    <input type="checkbox" checked={never} onChange={(event) => setNever(event.target.checked)} />
                    {t.never}
                </label>
                <p className={styles.help}>{t.later}</p>
                {error && (
                    <p className={styles.error} role="alert">
                        {error}
                    </p>
                )}
                <div className={styles.row}>
                    <button type="button" className={`${styles.btn} ${styles.go}`} onClick={close} autoFocus>
                        {t.ok}
                    </button>
                </div>
            </div>
        </div>
    );
}

/** Reads the interface from the backend and keeps it current. */
export default function InterfaceProvider() {
    const load = useCallback(async () => {
        try {
            applyInterface(await getJson<InterfaceState>("/api/interface"));
        } catch {
            // Not logged in yet, or the API is down: the language stays the remembered one.
        }
    }, []);

    useEffect(() => {
        const first = setTimeout(load, 0);
        window.addEventListener("focus", load);
        registerInterfaceLoader(load);
        return () => {
            clearTimeout(first);
            window.removeEventListener("focus", load);
            registerInterfaceLoader(null);
        };
    }, [load]);

    const approvals = useApprovalNotices();

    useWorkspaceEvents(
        ["interface.changed", ...APPROVAL_EVENTS],
        (event) => {
            if (event.type === "interface.changed") {
                applyInterface(event.data as unknown as InterfaceState);
            } else {
                approvals.onEvent(event);
            }
        },
        () => {
            void load();
            approvals.onConnect();
        },
    );

    return <VoiceLanguageNotice />;
}
