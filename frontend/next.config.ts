import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Hide the "Static route" / ISR badge in the corner during `next dev`.
  // (Next 15.1 uses appIsrStatus; 15.2+ also accepts `devIndicators: false`.)
  devIndicators: {
    appIsrStatus: false,
  },
};

export default nextConfig;
