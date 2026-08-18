/**
 * @file frontend/src/lib/utils.ts
 * @description Core module for A.U.R.O.R.A. System
 *
 * Implements primary logic and architectural constraints.
 *
 * Architectural constraints and responsibilities apply here.
 * Testability and dependency separation are enforced.
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}
