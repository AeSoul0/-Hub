/**
 * @file frontend/src/lib/utils.ts
 * @description Core module for A.U.R.O.R.A. System
 *
 * Implements core logic and architectural definitions.
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}
