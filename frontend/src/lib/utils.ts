/**
 * @file frontend/src/lib/utils.ts
 * @description Implements utils.ts.
 * 
 * This module manages the frontend logic for cn.
 * Core interfaces: data structures.
 */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}
