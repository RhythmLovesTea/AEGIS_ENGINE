import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  eslint: {
    // Keep checking enabled
    ignoreDuringBuilds: false,
  },
  typescript: {
    // Keep strict typechecking enabled during builds
    ignoreBuildErrors: false,
  },
};

export default nextConfig;
