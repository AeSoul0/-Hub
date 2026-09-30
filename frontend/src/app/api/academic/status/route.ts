/**
 * @file frontend/src/app/api/academic/status/route.ts
 * @description Proxy Route for Academic Verification and Polling.
 * 
 * This module acts as a Next.js API interceptor for polling the active state of an 
 * academic session. By proxying the request through the frontend server, it avoids 
 * CORS preflight constraints and securely passes the HttpOnly cookies directly to the 
 * underlying backend layer to accurately query session validity.
 */

import { fetchApi } from "@/lib/api/client";

export async function GET(request: Request) {
    try {
        const reqHeaders = new Headers(request.headers);
        const res = await fetchApi("/api/academic/status", {
            headers: {
                "Cookie": reqHeaders.get("cookie") || ""
            }
        });

        const data = await res.json();
        
        const resHeaders = new Headers();
        if (res.headers.has("set-cookie")) {
            resHeaders.set("Set-Cookie", res.headers.get("set-cookie") as string);
        }

        return Response.json(data, { status: res.status, headers: resHeaders });
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
