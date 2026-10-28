import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import DocumentsPage from "@/app/control-plane/documents/page";
import MemoryPage from "@/app/control-plane/memory/page";
import CitedText from "@/components/control-plane/CitedText";
import MemoryList from "@/components/control-plane/MemoryList";
import {
    formatSize,
    locatorLabel,
    memoryOn,
    splitCitations,
    type DocumentsView,
    type Memory,
    type MemoryView,
} from "@/lib/api/memory";
import { errorText } from "@/lib/nucleo/memory";

import { stubFetch } from "./helpers";

function memory(id: string, extra: Partial<Memory> = {}): Memory {
    return {
        id,
        kind: "fact",
        content: `Memory ${id}`,
        trusted: true,
        session_id: null,
        created_at: "2026-10-26T18:00:00",
        score: null,
        source: "user",
        ...extra,
    };
}

function settingsBody(values: Record<string, string> = {}) {
    const field = (name: string, value: string) => ({
        name,
        group: name === "AEHUB_DOCUMENTS_MAX_FILE_MB" ? "documents" : "memory",
        label: name,
        kind: "text",
        help: "",
        default: value,
        value: values[name] ?? value,
        source: "default",
        options: [],
    });
    return {
        settings: [
            field("AEHUB_MEMORY_ENABLED", "on"),
            field("AEHUB_MEMORY_MIN_SIMILARITY", "0.25"),
            field("AEHUB_EMBEDDER", "sentence-transformers"),
            field("AEHUB_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
            field("AEHUB_DOCUMENTS_MAX_FILE_MB", "5"),
        ],
    };
}

function lastBody(fetchMock: ReturnType<typeof stubFetch>, path: string, method: string): unknown {
    const call = [...fetchMock.mock.calls]
        .reverse()
        .find(([input, init]) => new URL(String(input)).pathname === path && init?.method === method);
    if (!call) {
        return undefined;
    }
    const body = call[1]?.body;
    return typeof body === "string" ? JSON.parse(body) : body;
}

function calledWith(fetchMock: ReturnType<typeof stubFetch>, fragment: string): boolean {
    return fetchMock.mock.calls.some(([input]) => String(input).includes(fragment));
}

describe("memory helpers", () => {
    it("splits citations, labels locations and reads the switch like the backend", () => {
        expect(splitCitations("At 7 [doc: notes/garden.md#L1-3], see [doc: plan.pdf#p2].")).toEqual([
            "At 7 ",
            { citation: "[doc: notes/garden.md#L1-3]", path: "notes/garden.md", locator: "L1-3" },
            ", see ",
            { citation: "[doc: plan.pdf#p2]", path: "plan.pdf", locator: "p2" },
            ".",
        ]);
        expect(splitCitations("No citation here.")).toEqual(["No citation here."]);
        expect(locatorLabel("L1-3")).toBe("righe 1-3");
        expect(locatorLabel("p2")).toBe("pagina 2");
        expect(memoryOn("0")).toBe(false);
        expect(memoryOn("off")).toBe(false);
        expect(memoryOn("1")).toBe(true);
        expect(memoryOn("on")).toBe(true);
        expect(formatSize(2048)).toBe("2.0 KB");
        expect(errorText("The same memory already exists.")).toBe("Lo stesso ricordo c'è già.");
        expect(errorText("Input rejected: jailbreak pattern")).toMatch(/cambiare le istruzioni/);
    });
});

describe("CitedText", () => {
    it("opens the passage a citation points to", async () => {
        stubFetch({
            "GET /api/documents/passage": () => ({
                status: 200,
                body: { path: "notes/garden.md", locator: "L1-3", content: "Water the tomatoes at 7." },
            }),
        });

        render(<CitedText text="At 7 [doc: notes/garden.md#L1-3]." />);

        expect(screen.queryByText(/doc:/)).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "garden.md · righe 1-3" }));

        const passage = await screen.findByRole("note", { name: "Passaggio citato" });
        expect(passage).toHaveTextContent("Water the tomatoes at 7.");
        fireEvent.click(screen.getByRole("button", { name: "garden.md · righe 1-3" }));
        expect(screen.queryByRole("note")).not.toBeInTheDocument();
    });

    it("says when a citation is not in the index", async () => {
        stubFetch({
            "GET /api/documents/passage": () => ({ status: 404, body: { detail: "This citation is not in the document index." } }),
        });

        render(<CitedText text="See [doc: made-up.md#L4-6]" />);
        fireEvent.click(screen.getByRole("button", { name: "made-up.md · righe 4-6" }));

        expect(await screen.findByText("Questa citazione non è nell'indice dei documenti.")).toBeInTheDocument();
    });
});

describe("MemoryList", () => {
    it("edits, vouches for and forgets a memory", async () => {
        const onSave = vi.fn(async () => true);
        const onForget = vi.fn();
        const untrusted = memory("m2", { content: "From a web page.", trusted: false, source: "agent", kind: "rule" });

        render(<MemoryList memories={[memory("m1"), untrusted]} onSave={onSave} onForget={onForget} />);

        expect(screen.getByText("affidabile")).toBeInTheDocument();
        expect(screen.getByText("non affidabile")).toBeInTheDocument();
        expect(screen.getByText(/salvato dall'agente/)).toBeInTheDocument();

        // Only the untrusted one can be vouched for.
        expect(screen.getAllByRole("button", { name: "Mi fido" })).toHaveLength(1);
        fireEvent.click(screen.getByRole("button", { name: "Mi fido" }));
        expect(onSave).toHaveBeenCalledWith(untrusted, { trusted: true });

        fireEvent.click(screen.getAllByRole("button", { name: "Modifica" })[0]);
        fireEvent.change(screen.getByLabelText("Testo del ricordo"), { target: { value: "Memory m1, edited." } });
        fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "preference" } });
        fireEvent.click(screen.getByRole("button", { name: "Salva" }));
        await waitFor(() =>
            expect(onSave).toHaveBeenLastCalledWith(memory("m1"), { content: "Memory m1, edited.", kind: "preference" }),
        );

        fireEvent.click(screen.getByRole("button", { name: "Dimentica regola m2" }));
        fireEvent.click(screen.getByRole("button", { name: "Conferma: dimentica" }));
        expect(onForget).toHaveBeenCalledWith(untrusted);
    });

    it("says when there is nothing", () => {
        render(<MemoryList memories={[]} onSave={vi.fn()} onForget={vi.fn()} />);
        expect(screen.getByText("Nessun ricordo qui.")).toBeInTheDocument();
    });
});

const MEMORY_VIEW: MemoryView = {
    memories: [
        memory("m1", { kind: "preference", content: "Answer in Italian." }),
        memory("m2", { content: "From a web page.", trusted: false, source: "agent" }),
    ],
    status: {
        enabled: true,
        embedder: "st:all-MiniLM-L6-v2",
        embedder_kind: "sentence-transformers",
        min_similarity: 0.25,
        total: 2,
        by_kind: { preference: 1, fact: 1 },
        untrusted: 1,
        stale_vectors: 2,
    },
};

describe("Memoria", () => {
    it("shows the memory, adds one, recomputes vectors and forgets the untrusted ones", async () => {
        const fetchMock = stubFetch({
            "GET /api/settings": () => ({ status: 200, body: settingsBody() }),
            "PUT /api/settings": () => ({ status: 200, body: settingsBody({ AEHUB_MEMORY_ENABLED: "off" }) }),
            "GET /api/memory": () => ({ status: 200, body: MEMORY_VIEW }),
            "POST /api/memory": () => ({ status: 201, body: { stored: 1, content: "x", kind: "rule" } }),
            "POST /api/memory/reembed": () => ({ status: 200, body: { memories: 2, documents: 5 } }),
            "DELETE /api/memory": () => ({ status: 200, body: { deleted: 1 } }),
        });

        render(<MemoryPage />);

        expect(await screen.findByText("2 ricordi")).toBeInTheDocument();
        expect(screen.getByText("1 non affidabili")).toBeInTheDocument();
        expect(await screen.findByText(/2 ricordi hanno i vettori di un altro modello/)).toBeInTheDocument();

        const add = screen.getByRole("form", { name: "Aggiungi un ricordo" });
        fireEvent.change(within(add).getByLabelText("Tipo"), { target: { value: "rule" } });
        fireEvent.change(within(add).getByLabelText("Testo"), { target: { value: "Never book flights before 9." } });
        fireEvent.click(within(add).getByRole("button", { name: "Salva" }));
        expect(await screen.findByText("Regola salvata: vale da ogni prossima run.")).toBeInTheDocument();
        expect(lastBody(fetchMock, "/api/memory", "POST")).toEqual({ content: "Never book flights before 9.", kind: "rule" });

        fireEvent.click(screen.getByRole("button", { name: "Ricalcola i vettori" }));
        expect(await screen.findByText("Vettori ricalcolati: 2 ricordi, 5 pezzi di documenti.")).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Dimentica i non affidabili" }));
        fireEvent.click(screen.getByRole("button", { name: "Conferma: dimentica 1" }));
        expect(await screen.findByText("1 ricordi non affidabili dimenticati.")).toBeInTheDocument();
        expect(calledWith(fetchMock, "scope=untrusted")).toBe(true);

        fireEvent.change(screen.getByRole("searchbox"), { target: { value: "italian" } });
        fireEvent.click(screen.getByRole("button", { name: "Cerca" }));
        await waitFor(() => expect(calledWith(fetchMock, "q=italian")).toBe(true));
    });

    it("turns the memory off and changes the embedder", async () => {
        const fetchMock = stubFetch({
            "GET /api/settings": () => ({ status: 200, body: settingsBody() }),
            "PUT /api/settings": () => ({ status: 200, body: settingsBody() }),
            "GET /api/memory": () => ({ status: 200, body: { ...MEMORY_VIEW, status: { ...MEMORY_VIEW.status, stale_vectors: 0 } } }),
        });

        render(<MemoryPage />);

        const card = await screen.findByRole("region", { name: "Come ricorda" });
        const save = within(card).getByRole("button", { name: "Salva" });
        expect(save).toBeDisabled();

        fireEvent.click(within(card).getByRole("switch", { name: "Memoria a lungo termine" }));
        fireEvent.click(within(card).getByRole("radio", { name: "Hash, senza modello" }));
        fireEvent.change(within(card).getByLabelText("Somiglianza minima"), { target: { value: "0.4" } });
        fireEvent.click(save);

        await waitFor(() =>
            expect(lastBody(fetchMock, "/api/settings", "PUT")).toEqual({
                values: { AEHUB_MEMORY_ENABLED: "off", AEHUB_MEMORY_MIN_SIMILARITY: "0.4", AEHUB_EMBEDDER: "hash" },
            }),
        );
    });
});

const DOCUMENTS: DocumentsView = {
    root: "C:/Users/me/Documents/ÆHub",
    root_exists: true,
    files: [
        { path: "notes/garden.md", size: 2048, chunks: 3, error: null, indexed_at: "2026-10-26T18:00:00" },
        { path: "scan.pdf", size: 9_000_000, chunks: 0, error: "File larger than 5 MB.", indexed_at: "2026-10-26T18:00:00" },
    ],
    max_file_mb: 5,
    suffixes: [".markdown", ".md", ".pdf", ".txt"],
    totals: { files: 2, chunks: 3, errors: 1 },
    stale_vectors: 0,
};

describe("Documenti", () => {
    it("syncs, uploads, searches and saves the size limit", async () => {
        const fetchMock = stubFetch({
            "GET /api/settings": () => ({ status: 200, body: settingsBody() }),
            "PUT /api/settings": () => ({ status: 200, body: settingsBody({ AEHUB_DOCUMENTS_MAX_FILE_MB: "10" }) }),
            "GET /api/documents": () => ({ status: 200, body: DOCUMENTS }),
            "POST /api/documents/sync": () => ({
                status: 200,
                body: { root: DOCUMENTS.root, root_exists: true, added: ["a.md"], updated: [], removed: ["old.md"], failed: [], unchanged: 2, pending: 0, truncated: false },
            }),
            "POST /api/documents/upload": () => ({
                status: 200,
                body: { path: "plan.md", sync: { root: DOCUMENTS.root, root_exists: true, added: ["plan.md"], updated: [], removed: [], failed: [], unchanged: 2, pending: 0, truncated: false } },
            }),
            "GET /api/documents/search": () => ({
                status: 200,
                body: { hits: [{ path: "notes/garden.md", locator: "L1-3", citation: "[doc: notes/garden.md#L1-3]", content: "Water the tomatoes at 7.", score: 1 }] },
            }),
        });

        render(<DocumentsPage />);

        expect(await screen.findByText("2 file · 3 pezzi")).toBeInTheDocument();
        expect(screen.getByText("1 non leggibili")).toBeInTheDocument();
        expect(screen.getByText("File larger than 5 MB.")).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Sincronizza ora" }));
        expect(await screen.findByText("Sincronizzato: 1 aggiunti, 1 tolti.")).toBeInTheDocument();

        const upload = screen.getByRole("form", { name: "Carica un documento" });
        const file = new File(["# Plan"], "plan.md", { type: "text/markdown" });
        fireEvent.change(within(upload).getByLabelText("File"), { target: { files: [file] } });
        fireEvent.click(within(upload).getByRole("checkbox", { name: "sostituisci se esiste" }));
        fireEvent.click(within(upload).getByRole("button", { name: "Carica" }));
        expect(await screen.findByText("plan.md caricato. Sincronizzato: 1 aggiunti.")).toBeInTheDocument();
        const form = lastBody(fetchMock, "/api/documents/upload", "POST") as FormData;
        expect(form).toBeInstanceOf(FormData);
        expect((form.get("file") as File).name).toBe("plan.md");
        expect(form.get("replace")).toBe("true");

        const search = screen.getByRole("region", { name: "Cerca nei documenti" });
        fireEvent.change(within(search).getByRole("searchbox"), { target: { value: "tomatoes" } });
        fireEvent.click(within(search).getByRole("button", { name: "Cerca" }));
        expect(await within(search).findByText("Water the tomatoes at 7.")).toBeInTheDocument();
        expect(within(search).getByText("righe 1-3")).toBeInTheDocument();

        fireEvent.change(screen.getByLabelText("Dimensione massima (MB)"), { target: { value: "10" } });
        fireEvent.click(within(screen.getByRole("region", { name: "Cartella di lavoro" })).getByRole("button", { name: "Salva" }));
        await waitFor(() =>
            expect(lastBody(fetchMock, "/api/settings", "PUT")).toEqual({ values: { AEHUB_DOCUMENTS_MAX_FILE_MB: "10" } }),
        );
    });

    it("explains a refused upload in Italian", async () => {
        stubFetch({
            "GET /api/settings": () => ({ status: 200, body: settingsBody() }),
            "GET /api/documents": () => ({ status: 200, body: DOCUMENTS }),
            "POST /api/documents/upload": () => ({
                status: 409,
                body: { detail: "A file with this name is already in the working folder." },
            }),
        });

        render(<DocumentsPage />);
        await screen.findByText("2 file · 3 pezzi");

        const upload = screen.getByRole("form", { name: "Carica un documento" });
        fireEvent.change(within(upload).getByLabelText("File"), {
            target: { files: [new File(["x"], "garden.md", { type: "text/markdown" })] },
        });
        fireEvent.click(within(upload).getByRole("button", { name: "Carica" }));

        expect(await screen.findByRole("alert")).toHaveTextContent(/C'è già un file con questo nome/);
    });
});
