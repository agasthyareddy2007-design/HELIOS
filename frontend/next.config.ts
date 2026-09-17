import type { NextConfig } from "next";

/**
 * HELIOS frontend configuration.
 *
 * The V1 API base URL and API key are read server-side only (see
 * src/app/api/helios/[...path]/route.ts). The key is deliberately NOT exposed
 * through a NEXT_PUBLIC_ variable so it never reaches the browser bundle.
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Pin the build root to this package so an unrelated lockfile higher up the
  // filesystem cannot influence module resolution.
  turbopack: {
    root: __dirname,
  },
  // GLSL shaders are authored as TypeScript template strings, so no custom
  // webpack loaders are required — keeps the build reliable.
  experimental: {
    optimizePackageImports: ["motion", "d3-scale", "d3-shape", "d3-array"],
  },
};

export default nextConfig;
