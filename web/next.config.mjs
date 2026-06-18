/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // We don't ship an eslint config in this scaffold; don't let lint block builds.
  eslint: { ignoreDuringBuilds: true },
};
export default nextConfig;
