/**
 * @file frontend/next.config.js
 * @description Core module for A.U.R.O.R.A. System
 *
 * Implements primary logic and architectural constraints.
 * Architectural constraints and responsibilities apply here.
 * Testability and dependency separation are enforced.
 */

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Allows mobile / external devices to access dev server
  allowedDevOrigins: [
    "192.168.1.216",
    "192.168.1.25:2003",
    "169.254.83.107:2003",
  ],
};

module.exports = nextConfig;