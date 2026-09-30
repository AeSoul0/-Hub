/**
 * @file frontend/src/lib/api/client.ts
 * @description Central API Client for A.U.R.O.R.A. Frontend
 * 
 * Provides a unified interface for all HTTP requests to the backend,
 * ensuring consistent base URLs, headers, and error handling.
 */

// We use process.env for Node.js environments (Next.js App Router API routes)
// and process.env.NEXT_PUBLIC_API_URL for the browser.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || process.env.API_URL || "http://127.0.0.1:3002";

export interface ApiClientOptions extends RequestInit {
  params?: Record<string, string | number | boolean>;
}

/**
 * Core fetch wrapper that automatically prepends the backend base URL.
 * 
 * @param endpoint The relative API endpoint (e.g., "/api/academic/status")
 * @param options Standard fetch options + optional query params
 * @returns The raw fetch Response
 */
export async function fetchApi(endpoint: string, options: ApiClientOptions = {}): Promise<Response> {
  let url = `${API_BASE_URL}${endpoint}`;
  
  if (options.params) {
    const searchParams = new URLSearchParams();
    Object.entries(options.params).forEach(([key, value]) => {
      searchParams.append(key, String(value));
    });
    url += `?${searchParams.toString()}`;
  }

  const { params, ...fetchOptions } = options;
  
  // Default headers can be injected here
  const headers = new Headers(fetchOptions.headers);
  if (!headers.has('Content-Type') && fetchOptions.method && fetchOptions.method !== 'GET') {
    headers.set('Content-Type', 'application/json');
  }

  return fetch(url, {
    ...fetchOptions,
    headers
  });
}

/**
 * Convenience method for GET requests, automatically parsing JSON.
 */
export async function getJson<T>(endpoint: string, options?: ApiClientOptions): Promise<T> {
  const res = await fetchApi(endpoint, { ...options, method: "GET" });
  if (!res.ok) {
    throw new Error(`HTTP Error ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

/**
 * Convenience method for POST requests, automatically stringifying the body and parsing JSON response.
 */
export async function postJson<T>(endpoint: string, body: any, options?: ApiClientOptions): Promise<T> {
  const res = await fetchApi(endpoint, {
    ...options,
    method: "POST",
    body: JSON.stringify(body)
  });
  if (!res.ok) {
    throw new Error(`HTTP Error ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}
