import type { NextConfig } from "next";
import { config } from "dotenv";
import { resolve } from "path";

// Load root .env so Firebase keys are available to the frontend
config({ path: resolve(__dirname, "../.env") });

const nextConfig: NextConfig = {
  output: "standalone",
  env: {
    FIREBASE_API_KEY: process.env.FIREBASE_API_KEY,
    FIREBASE_AUTH_DOMAIN: process.env.FIREBASE_AUTH_DOMAIN,
    FIREBASE_STORAGE_BUCKET: process.env.FIREBASE_STORAGE_BUCKET,
    FIREBASE_MESSAGING_SENDER_ID: process.env.FIREBASE_MESSAGING_SENDER_ID,
    FIREBASE_APP_ID: process.env.FIREBASE_APP_ID,
  },
};

export default nextConfig;
