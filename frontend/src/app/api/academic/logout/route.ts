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