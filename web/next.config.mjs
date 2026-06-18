/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // We don't ship an eslint config in this scaffold; don't let lint block builds.
  eslint: { ignoreDuringBuilds: true },
  // Static export: the app is fully client-rendered (SWR) and talks to the API
  // over HTTP, so it ships as static files. On DO App Platform it's a free
  // Static Site; same-origin /api routing means no CORS. `next dev` still works.
  output: "export",
  images: { unoptimized: true },
};
export default nextConfig;
