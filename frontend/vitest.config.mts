/**
 * @file frontend/vitest.config.mts
 * @description Vitest configuration: jsdom, the setup file, the `@` alias of src/.
 */
import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
    resolve: {
        alias: {
            "@": fileURLToPath(new URL("./src", import.meta.url)),
        },
    },
    test: {
        environment: "jsdom",
        setupFiles: ["./tests/setup.ts"],
        include: ["tests/**/*.test.{ts,tsx}"],
        // Node 25+ has its own localStorage, which hides jsdom's; tests use
        // jsdom's, like the browser (R1, Node 26 in CI).
        execArgv: ["--no-experimental-webstorage"],
    },
});
