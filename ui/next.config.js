/** @type {import('next').NextConfig} */
const webpack = require('webpack');

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone', // Enable standalone output for Docker

  webpack: (config, { isServer }) => {
    // CesiumJS configuration
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        path: false,
        crypto: false,
      };

      // Define CESIUM_BASE_URL at build time
      config.plugins.push(
        new webpack.DefinePlugin({
          CESIUM_BASE_URL: JSON.stringify('/'),
        })
      );
    }

    // Ignore cesium source maps
    config.ignoreWarnings = [/Failed to parse source map/];

    return config;
  },
};

module.exports = nextConfig;
