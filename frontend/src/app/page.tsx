/**
 * @file frontend/src/app/page.tsx
 * @description Home: the Nucleo (F1), behind the session check.
 */
"use client";

import AuthGate from "@/components/control-plane/AuthGate";
import Nucleo from "@/components/nucleo/Nucleo";

export default function Home() {
    return (
        <AuthGate>
            <Nucleo />
        </AuthGate>
    );
}
