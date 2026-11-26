/**
 * @file frontend/next.config.js
 * @description Next.js configuration: strict mode, the dev origins of the
 * LAN, with AEHUB_STATIC_EXPORT=1 the static export of the desktop app and
 * with AEHUB_STANDALONE=1 the standalone server of the Docker image.
 */

// AEHUB_STATIC_EXPORT=1: static files in out/ for the desktop app (M14,
// ADR-020), served by the backend from its own origin. Trailing slashes give
// every page its own folder with an index.html.
const staticExport = process.env.AEHUB_STATIC_EXPORT === "1";
// AEHUB_STANDALONE=1 (the Docker image, O1): a minimal server.js with only the
// node_modules it needs, run with `node server.js` (no npm process around it).
const standalone = process.env.AEHUB_STANDALONE === "1";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  ...(standalone && !staticExport && { output: "standalone" }),

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