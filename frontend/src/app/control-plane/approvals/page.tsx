/**
 * @file frontend/src/app/control-plane/approvals/page.tsx
 * @description Core module for A.U.R.O.R.A. System
 *
 * Implements primary logic and architectural constraints.
 * Architectural constraints and responsibilities apply here.
 * Testability and dependency separation are enforced.
 */

"use client";

import React, { useState } from 'react';

export default function ApprovalsPage() {
    const [approvals, setApprovals] = useState([
        { id: "app-101", task_id: "tsk-99", status: "WAITING_APPROVAL", description: "Deploy to Production", requested_by: "agent_runner" }
    ]);

    const handleApprove = (id: string) => {
        // Send approval to backend /workflows/engine.py
        console.log(`Approving ${id}`);
    };

    return (
        <div className="p-8 text-white min-h-screen" style={{ backgroundColor: '#111' }}>
            <h1 className="text-3xl font-bold mb-6 text-orange-500">M11 Control Plane: Human Approvals</h1>
            <table className="w-full text-left border-collapse">
                <thead>
                    <tr className="border-b border-gray-700">
                        <th className="p-2">ID</th>
                        <th className="p-2">Task</th>
                        <th className="p-2">Description</th>
                        <th className="p-2">Status</th>
                        <th className="p-2">Action</th>
                    </tr>
                </thead>
                <tbody>
                    {approvals.map(app => (
                        <tr key={app.id} className="border-b border-gray-800">
                            <td className="p-2 text-gray-400">{app.id}</td>
                            <td className="p-2">{app.task_id}</td>
                            <td className="p-2">{app.description}</td>
                            <td className="p-2 text-yellow-500">{app.status}</td>
                            <td className="p-2">
                                <button onClick={() => handleApprove(app.id)} className="bg-green-600 hover:bg-green-500 text-white px-4 py-1 rounded">Approve</button>
                                <button className="bg-red-600 hover:bg-red-500 text-white px-4 py-1 rounded ml-2">Reject</button>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
