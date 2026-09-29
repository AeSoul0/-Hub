/**
 * @file frontend/src/app/api/academic/login/route.ts
 * @description Core module for A.U.R.O.R.A. System
 *
 * Implements core logic and architectural definitions.
 */

/**
 * Academic Login API Route (Proxy Layer)
 * --------------------------------------
 * Triggers Playwright SPID authentication flow in backend.
 */

export async function POST() {
    try {
        const res = await fetch("http://localhost:3002/api/academic/login", {
            method: "POST",
        });

        const data = await res.json();

        return Response.json(data);
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
