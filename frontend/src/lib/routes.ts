/**
 * @file frontend/src/lib/routes.ts
 * @description Links to pages that take an id.
 *
 * The id travels in the query string, not in the path: the desktop app
 * serves the frontend as static files (M14, ADR-020), which have no
 * dynamic routes.
 */

export function runHref(runId: string): string {
    return `/control-plane/runs/view?id=${encodeURIComponent(runId)}`;
}
