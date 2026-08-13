import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets phones on the LAN load HMR assets when using `next dev`.
  allowedDevOrigins: ["*"],
};

export default nextConfig;
