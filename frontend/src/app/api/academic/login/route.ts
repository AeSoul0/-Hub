/**
 * @file frontend/src/app/api/academic/login/route.ts
 * @description Proxy Route for Academic Authentication via Playwright SPID.
 * 
 * This module manages the Next.js API route that acts as a reverse proxy for the backend's
 * academic login endpoint. It ensures that cross-origin credentials and CSRF tokens are 
 * properly forwarded between the user's browser and the FastAPI backend without exposing 
 * internal service URLs to the client side.
 */

import { fetchApi } from "@/lib/api/client";

export async function POST(request: Request) {
    try {
        const reqHeaders = new Headers(request.headers);
        
        const res = await fetchApi("/api/academic/login", {
            method: "POST",
            headers: {
                "Cookie": reqHeaders.get("cookie") || "",
                "Content-Type": "application/json"
            }
        });

        const data = await res.json();

        // Forward the backend Set-Cookie back to the client
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
