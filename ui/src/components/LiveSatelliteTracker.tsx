'use client';

/**
 * Live Satellite Tracker
 *
 * Real-time satellite position and gravity field visualization using WebSocket
 * streams from the API Gateway. Combines useTelemetryStream and useGravityStream
 * with the 3D GlobeViewer for live mission monitoring.
 */

import { useState, useEffect, useMemo } from 'react';
import GlobeViewer from './GlobeViewer';
import { useTelemetryStream, useGravityStream } from '@/hooks/useRealTimeStream';

interface LiveSatelliteTrackerProps {
  satelliteIds?: string[];
  showGravityOverlay?: boolean;
  autoRotate?: boolean;
}

export default function LiveSatelliteTracker({
  satelliteIds = [],
  showGravityOverlay: showGravityOverlayProp = true,
  autoRotate = false,
}: LiveSatelliteTrackerProps) {
  const [selectedSatellites, setSelectedSatellites] = useState<string[]>(satelliteIds);
  const [historyLength, setHistoryLength] = useState(50); // Number of historical positions to show as orbit traces
  const [showGravityOverlay, setShowGravityOverlay] = useState(showGravityOverlayProp);

  // Connect to real-time telemetry stream
  const telemetryStream = useTelemetryStream(selectedSatellites.length > 0 ? selectedSatellites : undefined);

  // Connect to real-time gravity stream
  const gravityStream = useGravityStream(selectedSatellites.length > 0 ? selectedSatellites : undefined);

  // Convert telemetry data to satellite positions for GlobeViewer
  const satellitePositions = useMemo(() => {
    const positions: any[] = [];
    telemetryStream.latestTelemetry.forEach((telem, satId) => {
      if (telem.location) {
        // Convert lat/lon/alt to ECEF Cartesian coordinates
        const lat = telem.location.latitude * Math.PI / 180;
        const lon = telem.location.longitude * Math.PI / 180;
        const alt = telem.location.altitude;

        // Earth radius in meters
        const R = 6378137.0;
        const h = alt;

        // ECEF conversion
        const x = (R + h) * Math.cos(lat) * Math.cos(lon);
        const y = (R + h) * Math.cos(lat) * Math.sin(lon);
        const z = (R + h) * Math.sin(lat);

        positions.push({
          time: new Date(telem.timestamp),
          position: [x, y, z] as [number, number, number],
          velocity: [0, 0, 0] as [number, number, number], // Velocity from telemetry if available
        });
      }
    });
    return positions;
  }, [telemetryStream.latestTelemetry]);

  // Convert telemetry history to orbit trajectories
  const orbitTrajectories = useMemo(() => {
    const trajectories: any[] = [];
    const satelliteHistories = new Map<string, typeof telemetryStream.telemetryHistory[0][]>();

    // Group history by satellite
    telemetryStream.telemetryHistory.slice(-historyLength).forEach(telem => {
      if (!satelliteHistories.has(telem.satellite_id)) {
        satelliteHistories.set(telem.satellite_id, []);
      }
      satelliteHistories.get(telem.satellite_id)!.push(telem);
    });

    // Convert to orbit trajectory format (positions in km)
    satelliteHistories.forEach((history, satId) => {
      if (history.length > 1) {
        const positions: [number, number, number][] = history.map(telem => {
          const lat = telem.location.latitude * Math.PI / 180;
          const lon = telem.location.longitude * Math.PI / 180;
          const alt = telem.location.altitude;
          const R = 6378137.0;
          const x = (R + alt) * Math.cos(lat) * Math.cos(lon) / 1000; // Convert to km
          const y = (R + alt) * Math.cos(lat) * Math.sin(lon) / 1000;
          const z = (R + alt) * Math.sin(lat) / 1000;
          return [x, y, z];
        });

        trajectories.push({
          id: satId,
          name: satId,
          positions,
          color: getSatelliteColor(satId),
          width: 2,
          showGroundTrack: true,
        });
      }
    });

    return trajectories;
  }, [telemetryStream.telemetryHistory, historyLength]);

  // Convert gravity data to measurements for GlobeViewer
  const gravityMeasurements = useMemo(() => {
    if (!showGravityOverlay) return [];

    const measurements: any[] = [];
    gravityStream.gravityHistory.slice(-100).forEach(grav => {
      if (grav.location) {
        const lat = grav.location.latitude * Math.PI / 180;
        const lon = grav.location.longitude * Math.PI / 180;
        const alt = grav.location.altitude;
        const R = 6378137.0;

        const x = (R + alt) * Math.cos(lat) * Math.cos(lon);
        const y = (R + alt) * Math.cos(lat) * Math.sin(lon);
        const z = (R + alt) * Math.sin(lat);

        measurements.push({
          position: [x, y, z] as [number, number, number],
          anomaly: grav.gravity_value || 0,
        });
      }
    });

    return measurements;
  }, [gravityStream.gravityHistory, showGravityOverlay]);

  // Helper to assign consistent colors to satellites
  function getSatelliteColor(satId: string): string {
    const colors = ['#FFD700', '#00FFFF', '#FF00FF', '#00FF00', '#FFA500'];
    const hash = satId.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    return colors[hash % colors.length];
  }

  return (
    <div className="relative w-full h-screen">
      {/* Status Panel */}
      <div className="absolute top-4 right-4 bg-gray-800/95 backdrop-blur-sm p-4 rounded-lg shadow-xl border border-gray-700 min-w-[300px] z-10">
        <h3 className="font-bold text-white mb-3 flex items-center gap-2">
          <span className="text-green-400">📡</span> Live Satellite Tracker
        </h3>

        {/* Connection Status */}
        <div className="space-y-2 mb-4">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-300">Telemetry Stream</span>
            <span className={`px-2 py-1 rounded text-xs font-medium ${
              telemetryStream.connected
                ? 'bg-green-500/20 text-green-400'
                : 'bg-red-500/20 text-red-400'
            }`}>
              {telemetryStream.status}
            </span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-300">Gravity Stream</span>
            <span className={`px-2 py-1 rounded text-xs font-medium ${
              gravityStream.connected
                ? 'bg-green-500/20 text-green-400'
                : 'bg-red-500/20 text-red-400'
            }`}>
              {gravityStream.status}
            </span>
          </div>
        </div>

        {/* Statistics */}
        <div className="space-y-2 border-t border-gray-700 pt-3">
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Tracked Satellites</span>
            <span className="text-white font-mono">{telemetryStream.latestTelemetry.size}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Telemetry Points</span>
            <span className="text-white font-mono">{telemetryStream.telemetryHistory.length}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Gravity Measurements</span>
            <span className="text-white font-mono">{gravityStream.gravityHistory.length}</span>
          </div>
        </div>

        {/* Latest Satellite Data */}
        {telemetryStream.latestTelemetry.size > 0 && (
          <div className="mt-4 border-t border-gray-700 pt-3">
            <h4 className="text-sm font-medium text-gray-300 mb-2">Active Satellites</h4>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {Array.from(telemetryStream.latestTelemetry.entries()).map(([satId, telem]) => (
                <div key={satId} className="bg-gray-900/50 p-2 rounded text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-white">{satId}</span>
                    <span className="text-gray-500">{new Date(telem.timestamp).toLocaleTimeString()}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-1 text-gray-400">
                    <div>Lat: <span className="text-green-400">{telem.location.latitude.toFixed(2)}°</span></div>
                    <div>Lon: <span className="text-blue-400">{telem.location.longitude.toFixed(2)}°</span></div>
                    <div>Alt: <span className="text-yellow-400">{(telem.location.altitude / 1000).toFixed(1)} km</span></div>
                    <div>Batt: <span className="text-purple-400">{telem.battery_level.toFixed(0)}%</span></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Controls */}
        <div className="mt-4 border-t border-gray-700 pt-3 space-y-2">
          <button
            onClick={() => {
              telemetryStream.clearHistory();
              gravityStream.clearHistory();
            }}
            className="w-full px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded transition"
          >
            Clear History
          </button>
          <div className="flex items-center justify-between">
            <label className="text-sm text-gray-300">Orbit Trail Length</label>
            <input
              type="range"
              min="10"
              max="200"
              value={historyLength}
              onChange={(e) => setHistoryLength(parseInt(e.target.value))}
              className="w-24"
            />
            <span className="text-sm text-gray-400 font-mono">{historyLength}</span>
          </div>
          <div className="flex items-center justify-between">
            <label className="text-sm text-gray-300">Gravity Overlay</label>
            <input
              type="checkbox"
              checked={showGravityOverlay}
              onChange={(e) => setShowGravityOverlay(e.target.checked)}
              className="w-4 h-4"
            />
          </div>
        </div>
      </div>

      {/* 3D Globe Viewer */}
      <GlobeViewer
        satellitePositions={satellitePositions}
        gravityData={gravityMeasurements}
        orbitTrajectories={orbitTrajectories}
        showOrbitPaths={true}
        showGroundTracks={true}
      />

      {/* No Connection Warning */}
      {!telemetryStream.connected && !gravityStream.connected && (
        <div className="absolute bottom-4 left-4 bg-yellow-500/20 border border-yellow-500 text-yellow-400 px-4 py-3 rounded-lg backdrop-blur-sm z-10">
          <p className="text-sm font-medium">⚠️ Not connected to real-time streams</p>
          <p className="text-xs mt-1">Check that the API Gateway WebSocket is running</p>
        </div>
      )}
    </div>
  );
}
