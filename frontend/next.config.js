/**
 * @file frontend/next.config.js
 * @description Core module for A.U.R.O.R.A. System
 *
 * Implements primary logic and architectural constraints.
 * Architectural constraints and responsibilities apply here.
 * Testability and dependency separation are enforced.
 */

// AEHUB_STATIC_EXPORT=1: static files in out/ for the desktop app (M14,
// ADR-020), served by the backend from its own origin. Trailing slashes give
// every page its own folder with an index.html.
const staticExport = process.env.AEHUB_STATIC_EXPORT === "1";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  ...(staticExport && {
    output: "export",
    trailingSlash: true,
    images: { unoptimized: true },
    env: { NEXT_PUBLIC_AEHUB_SAME_ORIGIN: "1" },
  }),

  // Allows mobile / external devices to access dev server
  allowedDevOrigins: [
    "192.168.1.216",
    "192.168.1.25:2003",
    "169.254.83.107:2003",
  ],
};

module.exports = nextConfig;