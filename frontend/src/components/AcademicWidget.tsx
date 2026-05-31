"use client";

import { useEffect, useState } from "react";

type AcademicData = {
    gpa: number;
    exams: number;
    cfu: number;
};

const DEFAULT_DATA: AcademicData = {
    gpa: 0,
    exams: 0,
    cfu: 0,
};

export default function AcademicWidget() {
    const [data, setData] = useState<AcademicData>(DEFAULT_DATA);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const controller = new AbortController();

        async function loadAcademic() {
            try {
                setLoading(true);
                setError(null);

                const res = await fetch("/api/academic/status", {
                    method: "GET",
                    signal: controller.signal,
                });

                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}`);
                }

                const json = await res.json();

                const d = json?.data;

                setData({
                    gpa: typeof d?.gpa === "number" ? d.gpa : 0,
                    exams: typeof d?.exams === "number" ? d.exams : 0,
                    cfu: typeof d?.cfu === "number" ? d.cfu : 0,
                });
            } catch (e: any) {
                if (e?.name !== "AbortError") {
                    console.error("Academic fetch failed:", e);
                    setError("Data unavailable");
                }
            } finally {
                setLoading(false);
            }
        }

        loadAcademic();

        return () => controller.abort();
    }, []);

    return (
        <div className="p-4 rounded-xl border shadow-sm bg-white">
            <h2 className="text-lg font-semibold mb-3">
                Academic Status
            </h2>

            {/* KEEP ORIGINAL LOGIC VISUAL OUTPUT UNCHANGED */}

            {loading && (
                <p className="text-gray-500">
                    Loading academic data...
                </p>
            )}

            {error && (
                <p className="text-red-500 text-sm">
                    {error}
                </p>
            )}

            {/* DO NOT CHANGE DATA STRUCTURE (important for Playwright stability) */}
            {!loading && (
                <div>
                    <p>GPA: {data.gpa}</p>
                    <p>Exams: {data.exams}</p>
                    <p>CFU: {data.cfu}</p>
                </div>
            )}
        </div>
    );
}