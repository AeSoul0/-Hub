import { describe, expect, it } from "vitest";

import { ApiError, deleteJson, getJson } from "@/lib/api/client";

import { stubFetch } from "./helpers";

describe("API client", () => {
    it("sends the session cookie", async () => {
        const fetch = stubFetch({ "GET /api/runs/live": () => ({ status: 200, body: { runs: [] } }) });

        await expect(getJson("/api/runs/live")).resolves.toEqual({ runs: [] });
        expect(fetch.mock.calls[0][1]?.credentials).toBe("include");
    });

    it("raises ApiError with the status and the backend detail", async () => {
        stubFetch({
            "DELETE /api/memory/m1": () => ({ status: 404, body: { detail: "No memory with this id in your scope." } }),
        });

        const error = (await deleteJson("/api/memory/m1").catch((err: unknown) => err)) as ApiError;

        expect(error).toBeInstanceOf(ApiError);
        expect(error.status).toBe(404);
        expect(error.message).toBe("No memory with this id in your scope.");
    });
});
