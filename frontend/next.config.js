/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // The browser calls the API directly (see src/lib/api.ts). It is not proxied through Next.js
  // because a proxy would buffer the server-sent events that carry planning progress.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
};

module.exports = nextConfig;
