/**
 * @file frontend/src/lib/i18n.tsx
 * @description The interface language (ADR-034): English by default, or
 * Italian. The choice is the backend setting AEHUB_UI_LANGUAGE, so
 * IMPOSTAZIONI and Aurora change it the same way. GET /api/interface gives
 * it to every page, and `interface.changed` switches the open pages at once.
 * This browser keeps a copy only to paint the first screen in the right
 * language.
 *
 * Text sits next to the code that shows it, as a catalog with one entry per
 * language: `catalog({ en: {...}, it: {...} })`. The Italian entry must
 * have the shape of the English one, so a missing translation is a type
 * error. A new language is one more entry in each catalog and in LANGS.
 */
"use client";

import { useSyncExternalStore } from "react";

export type Lang = "en" | "it";

export const LANGS: { value: Lang; label: string }[] = [
    { value: "en", label: "English" },
    { value: "it", label: "Italiano" },
];

export const DEFAULT_LANG: Lang = "en";

/** What GET /api/interface returns. */
export interface InterfaceState {
    language: Lang;
    voice_language_warning: boolean;
    voice: {
        enabled: boolean;
        engine: string;
        name: string;
        /** The language the chosen voice speaks; null when it cannot be known. */
        language: string | null;
    };
    /** The wake word (N2, ADR-041); "off" when the microphone must be pressed. */
    wake?: { word: string; label: string; threshold: number };
}

const STORAGE_KEY = "aehub.language";

export function isLang(value: unknown): value is Lang {
    return LANGS.some((lang) => lang.value === value);
}

function storedLanguage(): Lang {
    try {
        const stored = window.localStorage.getItem(STORAGE_KEY);
        return isLang(stored) ? stored : DEFAULT_LANG;
    } catch {
        return DEFAULT_LANG;
    }
}

// The interface as last read from the backend; null until then.
let backend: InterfaceState | null = null;
// The language chosen on this page before the backend confirmed it.
let chosen: Lang | null = null;
const listeners = new Set<() => void>();

function notify(): void {
    listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

function currentLanguage(): Lang {
    return chosen ?? backend?.language ?? storedLanguage();
}

function remember(lang: Lang): void {
    try {
        window.localStorage.setItem(STORAGE_KEY, lang);
    } catch {
        // Storage refused (private window): the backend still has the choice.
    }
    if (typeof document !== "undefined") {
        document.documentElement.lang = lang;
    }
}

/** A new state from the backend (GET /api/interface or `interface.changed`). */
export function applyInterface(state: InterfaceState): void {
    backend = { ...state, language: isLang(state.language) ? state.language : DEFAULT_LANG };
    chosen = null;
    remember(backend.language);
    notify();
}

/** Switch the pages now; the caller saves AEHUB_UI_LANGUAGE. */
export function chooseLanguage(lang: Lang): void {
    chosen = lang;
    if (backend) {
        backend = { ...backend, language: lang };
    }
    remember(lang);
    notify();
}

/** Show or hide the voice notice now; the caller saves the setting. */
export function chooseVoiceWarning(enabled: boolean): void {
    if (backend) {
        backend = { ...backend, voice_language_warning: enabled };
        notify();
    }
}

// The InterfaceProvider's loader, so a login can read the interface at once.
let loader: (() => void) | null = null;

export function registerInterfaceLoader(load: (() => void) | null): void {
    loader = load;
}

/** Read GET /api/interface again (after a login). */
export function refreshInterface(): void {
    loader?.();
}

/** For tests: forget the backend state. */
export function resetInterface(): void {
    backend = null;
    chosen = null;
    notify();
}

/** The interface language; every page re-renders when it changes. */
export function useLanguage(): Lang {
    return useSyncExternalStore(subscribe, currentLanguage, () => DEFAULT_LANG);
}

/** The whole interface state, null until the backend answered. */
export function useInterface(): InterfaceState | null {
    return useSyncExternalStore(
        subscribe,
        () => backend,
        () => null,
    );
}

export type Catalog<T> = Record<Lang, T>;

/** The text of one area in every language; Italian must match the English shape. */
export function catalog<T>(texts: { en: T; it: NoInfer<T> }): Catalog<T> {
    return texts;
}

/** The text of a catalog in the current language. */
export function useText<T>(texts: Catalog<T>): T {
    return texts[useLanguage()];
}

/** The locale for dates and numbers. */
export function localeOf(lang: Lang): string {
    return lang === "it" ? "it-IT" : "en-GB";
}

/** Names of the languages a voice may speak, in each interface language. */
export const LANGUAGE_NAMES = catalog<Record<string, string>>({
    en: { en: "English", it: "Italian", es: "Spanish", fr: "French", de: "German", pt: "Portuguese" },
    it: { en: "inglese", it: "italiano", es: "spagnolo", fr: "francese", de: "tedesco", pt: "portoghese" },
});
