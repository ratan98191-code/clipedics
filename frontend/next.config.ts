import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow video src from the local API server
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "localhost", port: "8000" },
    ],
  },
};

export default nextConfig;
