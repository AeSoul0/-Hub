/**
 * Academic Status API Route (Proxy Layer)
 * ---------------------------------------
 * Forwards request to FastAPI backend to avoid CORS issues.
 * This ensures frontend never directly communicates with external services.
 */

export async function GET() {
    try {
        const res = await fetch("http://localhost:3002/api/academic/status");

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
