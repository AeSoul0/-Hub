/**
 * @file frontend/src/lib/api/client.ts
 * @description Centralized HTTP client for the A.U.R.O.R.A. frontend.
 *
 * Provides a single transport boundary for backend communication with:
 * - a consistent API base URL;
 * - optional query-string parameters;
 * - browser-compatible request headers;
 * - JSON convenience helpers.
 *
 * The client deliberately preserves browser-managed multipart headers for
 * FormData and binary request bodies.
 */

// ============================================================================
// API CONFIGURATION
// ============================================================================

export const API_BASE_URL =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.API_URL ||
    "http://127.0.0.1:3002";

// ============================================================================
// REQUEST TYPES
// ============================================================================

export interface ApiClientOptions extends RequestInit {
    params?: Record<string, string | number | boolean>;
}

// ============================================================================
// CORE HTTP CLIENT
// ============================================================================

/**
 * Executes an HTTP request against the configured backend.
 *
 * @param endpoint Relative backend endpoint, for example "/api/health".
 * @param options Standard fetch options plus optional query parameters.
 * @returns The raw backend response.
 */
export async function fetchApi(
    endpoint: string,
    options: ApiClientOptions = {},
): Promise<Response> {
    const { params, ...fetchOptions } = options;
    const url = new URL(endpoint, API_BASE_URL);

    if (params) {
        Object.entries(params).forEach(([key, value]) => {
            url.searchParams.set(key, String(value));
        });
    }

    const headers = new Headers(fetchOptions.headers);
    const body = fetchOptions.body;

    // Preserve browser-managed multipart boundaries and binary content types.
    const isFormDataBody =
        typeof FormData !== "undefined" && body instanceof FormData;
    const isBlobBody =
        typeof Blob !== "undefined" && body instanceof Blob;
    const isUrlEncodedBody =
        typeof URLSearchParams !== "undefined" &&
        body instanceof URLSearchParams;
    const isArrayBufferBody =
        typeof ArrayBuffer !== "undefined" &&
        (body instanceof ArrayBuffer ||
            ArrayBuffer.isView(body as ArrayBufferView));

    // JSON content type is inferred only for plain string bodies when the
    // caller has not explicitly selected a transport format.
    if (
        !headers.has("Content-Type") &&
        body !== undefined &&
        !isFormDataBody &&
        !isBlobBody &&
        !isUrlEncodedBody &&
        !isArrayBufferBody &&
        typeof body === "string"
    ) {
        headers.set("Content-Type", "application/json");
    }

    return fetch(url.toString(), {
        ...fetchOptions,
        headers,
        credentials: "include",
    });
}

// ============================================================================
// JSON HELPERS
// ============================================================================

/**
 * Executes a GET request and parses the JSON response.
 */
export async function getJson<T>(
    endpoint: string,
    options?: ApiClientOptions,
): Promise<T> {
    const response = await fetchApi(endpoint, {
        ...options,
        method: "GET",
    });

    if (!response.ok) {
        throw new Error(
            `HTTP request failed with status ${response.status}: ${response.statusText}`,
        );
    }

    return response.json() as Promise<T>;
}

/**
 * Executes a JSON POST request and parses the JSON response.
 */
export async function postJson<T>(
    endpoint: string,
    body: unknown,
    options?: ApiClientOptions,
): Promise<T> {
    const headers = new Headers(options?.headers);
    if (!headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }

    const response = await fetchApi(endpoint, {
        ...options,
        method: "POST",
        headers,
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        throw new Error(
            `HTTP request failed with status ${response.status}: ${response.statusText}`,
        );
    }

    return response.json() as Promise<T>;
}
