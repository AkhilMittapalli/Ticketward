import type { NextConfig } from "next";

// Baseline hardening headers. The nonce-based Content-Security-Policy is added in P8/P9
// (Next 16 `proxy.ts` or the Caddy reverse proxy) together with same-origin /api routing;
// HSTS is set by the TLS terminator (Caddy, P9).
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  {
    key: "Permissions-Policy",
    value:
      "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()",
  },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  typedRoutes: true,
  // No image optimizer endpoint: nothing to proxy or abuse, no sharp native build.
  images: { unoptimized: true },
  headers() {
    return Promise.resolve([{ source: "/:path*", headers: securityHeaders }]);
  },
};

export default nextConfig;
