/**
 * @file frontend/tests/setup.ts
 * @description Vitest setup: jest-dom matchers and cleanup after each test.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { resetInterface } from "@/lib/i18n";

afterEach(() => {
    cleanup();
    // Each test starts in English, with no interface state from the backend.
    window.localStorage.clear();
    window.sessionStorage.clear();
    resetInterface();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
});
