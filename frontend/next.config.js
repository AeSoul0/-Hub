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