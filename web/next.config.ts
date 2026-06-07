import type { NextConfig } from "next";
import { readFileSync } from "fs";
import { resolve } from "path";

function readVersionFromPyproject(): string {
  try {
    const content = readFileSync(resolve(__dirname, "..", "pyproject.toml"), "utf-8");
    const match = content.match(/^version\s*=\s*"([^"]+)"/m);
    return match?.[1] ?? "0.0.0";
  } catch {
    return "0.0.0";
  }
}

const nextConfig: NextConfig = {
  devIndicators: false,
  env: {
    NEXT_PUBLIC_APP_VERSION: readVersionFromPyproject(),
  },
  async rewrites() {
    return [
      {
        source: "/api-proxy/:path*",
        destination: "http://127.0.0.1:8000/:path*",
      },
    ];
  },
};

export default nextConfig;
