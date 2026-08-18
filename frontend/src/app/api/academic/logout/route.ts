/**
 * @file frontend/src/app/api/academic/logout/route.ts
 * @description Core module for A.U.R.O.R.A. System
 *
 * Implements primary logic and architectural constraints.
 *
 * Architectural constraints and responsibilities apply here.
 * Testability and dependency separation are enforced.
 */

/**
 * Academic Logout API Route (Proxy Layer)
 * ---------------------------------------
 * Clears cached academic session in backend.
 */

export async function POST() {
    try {
        const res = await fetch("http://localhost:3002/api/academic/logout", {
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
