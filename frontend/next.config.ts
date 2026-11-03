import path from "node:path";
import type { NextConfig } from "next";

// Rewrites are resolved when `next build` runs (and baked into the standalone
// server), so API_INTERNAL_URL must be present at build time. In Docker it is a
// build ARG that defaults to http://api:8000; locally it defaults to :8100.
const API_INTERNAL_URL = (process.env.API_INTERNAL_URL || "http://localhost:8100").replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  // Several lockfiles exist up the tree; pin tracing to this app.
  outputFileTracingRoot: path.join(__dirname),
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_INTERNAL_URL}/api/:path*` }];
  },
};

export default nextConfig;
