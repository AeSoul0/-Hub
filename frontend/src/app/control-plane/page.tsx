/**
 * @file frontend/src/app/control-plane/page.tsx
 * @description The Control Plane opens on the approval queue.
 */
import { redirect } from "next/navigation";

export default function ControlPlaneIndex() {
    redirect("/control-plane/approvals");
}
