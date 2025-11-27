'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useState } from 'react';

// Dynamically import GlobeViewer to avoid SSR issues with Cesium
const GlobeViewer = dynamic(() => import('../components/GlobeViewer'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full bg-gray-900">
      <div className="text-center">
        <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-500 mx-auto mb-4"></div>
        <p className="text-gray-400">Loading 3D Globe Viewer...</p>
      </div>
    </div>
  ),
});

export default function Home() {
  const [showGlobe, setShowGlobe] = useState(false);
  const [satelliteData, setSatelliteData] = useState([]);
  const [gravityData, setGravityData] = useState([]);

  return (
    <main className="min-h-screen bg-gray-900">
      <div className="fixed top-0 left-0 right-0 bg-gradient-to-r from-blue-900 to-purple-900 border-b border-gray-800 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <span className="text-3xl">🛰️</span>
              <div>
                <h1 className="text-xl font-bold text-white">GALILEO</h1>
                <p className="text-xs text-gray-300">Geospatial Analytics & Intelligence</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Link
                href="/dashboard"
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-3zM14 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1h-4a1 1 0 01-1-1v-3z" />
                </svg>
                Mission Dashboard
              </Link>
              <div className="flex items-center gap-2 px-3 py-1.5 bg-green-900/30 rounded-full border border-green-700/50">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                <span className="text-sm text-green-400">System Online</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="pt-16 h-screen">
        {showGlobe ? (
          <GlobeViewer
            satellitePositions={satelliteData}
            gravityData={gravityData}
            showGrid={true}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full bg-gradient-to-b from-gray-900 via-blue-900/20 to-gray-900">
            <div className="text-center max-w-2xl px-4">
              <div className="text-8xl mb-6">🛰️</div>
              <h2 className="text-4xl font-bold text-white mb-4">GALILEO</h2>
              <p className="text-lg text-gray-300 mb-2">
                Geospatial Analytics, Learning, and Intelligence for Land, Environment & Oceanography
              </p>
              <p className="text-md text-gray-400 mb-8">
                AI-Enhanced Space-Based Platform for Next-Generation Earth Observation
              </p>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
                  <div className="text-3xl font-bold text-blue-400">135+</div>
                  <div className="text-sm text-gray-400">API Endpoints</div>
                </div>
                <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
                  <div className="text-3xl font-bold text-green-400">11</div>
                  <div className="text-sm text-gray-400">Service Modules</div>
                </div>
                <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
                  <div className="text-3xl font-bold text-purple-400">PINN</div>
                  <div className="text-sm text-gray-400">ML Integration</div>
                </div>
                <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
                  <div className="text-3xl font-bold text-yellow-400">Real-Time</div>
                  <div className="text-sm text-gray-400">WebSocket</div>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Link
                  href="/dashboard"
                  className="px-8 py-4 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-3zM14 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1h-4a1 1 0 01-1-1v-3z" />
                  </svg>
                  Open Mission Dashboard
                </Link>
                <button
                  onClick={() => setShowGlobe(true)}
                  className="px-8 py-4 bg-gray-700 hover:bg-gray-600 text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Launch 3D Globe
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="fixed bottom-4 right-4 bg-gray-800 border border-gray-700 rounded-lg p-4 shadow-xl max-w-md z-20">
        <h3 className="text-sm font-semibold text-white mb-2">Quick Stats</h3>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-gray-900 rounded p-2">
            <div className="text-gray-400">Python Modules</div>
            <div className="text-lg font-bold text-blue-400">38</div>
          </div>
          <div className="bg-gray-900 rounded p-2">
            <div className="text-gray-400">Lines of Code</div>
            <div className="text-lg font-bold text-purple-400">13.8K</div>
          </div>
          <div className="bg-gray-900 rounded p-2">
            <div className="text-gray-400">API Uptime</div>
            <div className="text-lg font-bold text-green-400">99.9%</div>
          </div>
          <div className="bg-gray-900 rounded p-2">
            <div className="text-gray-400">Active Sims</div>
            <div className="text-lg font-bold text-yellow-400">0</div>
          </div>
        </div>
        <div className="mt-3 flex gap-2">
          <a
            href="http://localhost:4001/docs"
            target="_blank"
            className="flex-1 text-center px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded transition-colors"
          >
            API Docs
          </a>
          <a
            href="https://github.com/alovladi007/GALILEO-V2.0"
            target="_blank"
            className="flex-1 text-center px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white text-xs rounded transition-colors"
          >
            GitHub
          </a>
        </div>
      </div>
    </main>
  );
}
