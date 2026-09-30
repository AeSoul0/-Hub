/**
 * @file frontend/src/app/api/academic/logout/route.ts
 * @description Proxy Route for Academic Session Termination.
 * 
 * This module manages the Next.js API route that acts as a reverse proxy for the backend's
 * academic logout endpoint. It ensures that session deletion requests are correctly routed 
 * with the necessary cookie payloads, effectively terminating the user's active session 
 * across both the frontend proxy and the backend identity manager.
 */

import { fetchApi } from "@/lib/api/client";

export async function POST(request: Request) {
    try {
        const reqHeaders = new Headers(request.headers);
        const res = await fetchApi("/api/academic/logout", {
            method: "POST",
            headers: {
                "Cookie": reqHeaders.get("cookie") || ""
            }
        });

        const data = await res.json();

        const resHeaders = new Headers();
        if (res.headers.has("set-cookie")) {
            resHeaders.set("Set-Cookie", res.headers.get("set-cookie") as string);
        }

        return Response.json(data, { headers: resHeaders });
    } catch (error) {
        return Response.json(
            {
                status: "error",
                message: "Backend unreachable",
            },
            { status: 500 }
        );
    }
}
