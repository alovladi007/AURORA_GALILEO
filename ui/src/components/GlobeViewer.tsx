'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import * as Cesium from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';

interface SatellitePosition {
  time: Date;
  position: [number, number, number]; // [x, y, z] in meters (ECEF)
  velocity: [number, number, number];
}

interface GravityMeasurement {
  position: [number, number, number];
  anomaly: number; // mGal
}

interface OrbitTrajectory {
  id: string;
  name: string;
  positions: [number, number, number][]; // Array of [x, y, z] in km (ECI/ECEF)
  times?: number[]; // Optional timestamps in seconds
  color?: string;
  width?: number;
  showGroundTrack?: boolean;
}

interface FormationSatellite {
  id: string;
  name: string;
  positions: [number, number, number][]; // Trajectory positions
  color?: string;
}

interface GlobeViewerProps {
  satellitePositions?: SatellitePosition[];
  gravityData?: GravityMeasurement[];
  showGrid?: boolean;
  // New props for orbit visualization
  orbitTrajectories?: OrbitTrajectory[];
  formationSatellites?: FormationSatellite[];
  showOrbitPaths?: boolean;
  showGroundTracks?: boolean;
  animationEnabled?: boolean;
  currentTime?: number; // Index into trajectory arrays
  onTimeChange?: (time: number) => void;
}

export default function GlobeViewer({
  satellitePositions = [],
  gravityData = [],
  showGrid = false,
  orbitTrajectories = [],
  formationSatellites = [],
  showOrbitPaths = true,
  showGroundTracks = false,
  animationEnabled = false,
  currentTime = 0,
  onTimeChange,
}: GlobeViewerProps) {
  const viewerContainerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const orbitEntitiesRef = useRef<Map<string, Cesium.Entity>>(new Map());
  const satelliteEntitiesRef = useRef<Map<string, Cesium.Entity>>(new Map());
  const [selectedPoint, setSelectedPoint] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [animationIndex, setAnimationIndex] = useState(0);

  // Color palette for satellites
  const satelliteColors = [
    Cesium.Color.YELLOW,
    Cesium.Color.CYAN,
    Cesium.Color.MAGENTA,
    Cesium.Color.LIME,
    Cesium.Color.ORANGE,
  ];

  // Convert ECI/ECEF km positions to Cartesian3 (meters)
  const positionsToCartesian3 = useCallback((positions: [number, number, number][]) => {
    return positions.map(pos =>
      new Cesium.Cartesian3(pos[0] * 1000, pos[1] * 1000, pos[2] * 1000)
    );
  }, []);

  // Convert Cartesian3 to Lat/Lon for ground track
  const getGroundTrack = useCallback((positions: [number, number, number][]) => {
    return positions.map(pos => {
      const cartesian = new Cesium.Cartesian3(pos[0] * 1000, pos[1] * 1000, pos[2] * 1000);
      const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
      return Cesium.Cartesian3.fromRadians(
        cartographic.longitude,
        cartographic.latitude,
        0 // Ground level
      );
    });
  }, []);

  useEffect(() => {
    console.log('[GlobeViewer] useEffect triggered');
    console.log('[GlobeViewer] containerRef.current:', viewerContainerRef.current);

    if (!viewerContainerRef.current) {
      console.error('[GlobeViewer] containerRef is null, returning early');
      return;
    }

    const initCesium = async () => {
      try {
        console.log('[GlobeViewer] Starting Cesium initialization...');

        // Set Cesium Ion token
        const token = process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN || 'your-token-here';
        console.log('[GlobeViewer] Setting Ion token:', token.substring(0, 20) + '...');
        Cesium.Ion.defaultAccessToken = token;

        // Set Cesium base URL for assets (Workers, etc.)
        (window as any).CESIUM_BASE_URL = '/';
        console.log('[GlobeViewer] CESIUM_BASE_URL set to:', (window as any).CESIUM_BASE_URL);

        // Configure Cesium to load assets from public directory
        if ((Cesium as any).buildModuleUrl) {
          (Cesium as any).buildModuleUrl.setBaseUrl('/');
          console.log('[GlobeViewer] buildModuleUrl.setBaseUrl set to /');
        }

        console.log('[GlobeViewer] About to create Cesium Viewer...');

        // Create the Viewer with offline imagery configuration
        const viewer = new Cesium.Viewer(viewerContainerRef.current!, {
          animation: false,
          baseLayerPicker: false,
          fullscreenButton: false,
          geocoder: false,
          homeButton: true,
          infoBox: true,
          sceneModePicker: false,
          selectionIndicator: true,
          timeline: false,
          navigationHelpButton: false,
          navigationInstructionsInitiallyVisible: false,
          // Use offline Natural Earth II imagery - works without Ion token issues
          baseLayer: Cesium.ImageryLayer.fromProviderAsync(
            Cesium.TileMapServiceImageryProvider.fromUrl(
              Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII")
            )
          ),
        });

        console.log('[GlobeViewer] ✅ Cesium Viewer created successfully!');
        console.log('[GlobeViewer] Viewer object:', viewer);

        viewerRef.current = viewer;

        // Add satellite positions if provided
        if (satellitePositions.length > 0) {
          satellitePositions.forEach((satPos, index) => {
            viewer.entities.add({
              name: `Satellite ${index + 1}`,
              position: Cesium.Cartesian3.fromArray(satPos.position),
              point: {
                pixelSize: 10,
                color: Cesium.Color.YELLOW,
                outlineColor: Cesium.Color.BLACK,
                outlineWidth: 2,
              },
            });
          });
        }

        // Add gravity measurements if provided
        if (gravityData.length > 0) {
          gravityData.forEach((measurement, index) => {
            const normalized = (measurement.anomaly + 100) / 200;
            const clamped = Math.max(0, Math.min(1, normalized));
            const color = Cesium.Color.fromHsl((1 - clamped) * 0.6, 0.8, 0.5);

            viewer.entities.add({
              name: `Gravity Anomaly ${index}`,
              position: Cesium.Cartesian3.fromArray(measurement.position),
              point: {
                pixelSize: 8,
                color: color,
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 1,
              },
            });
          });
        }

        // Add orbit trajectories
        if (orbitTrajectories.length > 0 && showOrbitPaths) {
          console.log('[GlobeViewer] Adding orbit trajectories:', orbitTrajectories.length);
          orbitTrajectories.forEach((trajectory, index) => {
            const color = trajectory.color
              ? Cesium.Color.fromCssColorString(trajectory.color)
              : satelliteColors[index % satelliteColors.length];

            // Convert positions to Cartesian3
            const cartesianPositions = positionsToCartesian3(trajectory.positions);

            // Add orbit path polyline
            const orbitEntity = viewer.entities.add({
              name: `${trajectory.name} Orbit`,
              polyline: {
                positions: cartesianPositions,
                width: trajectory.width || 2,
                material: new Cesium.PolylineGlowMaterialProperty({
                  glowPower: 0.2,
                  color: color,
                }),
                clampToGround: false,
              },
            });
            orbitEntitiesRef.current.set(`orbit-${trajectory.id}`, orbitEntity);

            // Add ground track if enabled
            if (showGroundTracks || trajectory.showGroundTrack) {
              const groundTrackPositions = getGroundTrack(trajectory.positions);
              const groundTrackEntity = viewer.entities.add({
                name: `${trajectory.name} Ground Track`,
                polyline: {
                  positions: groundTrackPositions,
                  width: 1,
                  material: color.withAlpha(0.5),
                  clampToGround: true,
                },
              });
              orbitEntitiesRef.current.set(`ground-${trajectory.id}`, groundTrackEntity);
            }

            // Add current satellite position marker
            if (trajectory.positions.length > 0) {
              const currentPosIndex = Math.min(currentTime, trajectory.positions.length - 1);
              const currentPos = trajectory.positions[currentPosIndex];
              const satEntity = viewer.entities.add({
                name: trajectory.name,
                position: new Cesium.Cartesian3(
                  currentPos[0] * 1000,
                  currentPos[1] * 1000,
                  currentPos[2] * 1000
                ),
                point: {
                  pixelSize: 12,
                  color: color,
                  outlineColor: Cesium.Color.WHITE,
                  outlineWidth: 2,
                },
                label: {
                  text: trajectory.name,
                  font: '12px sans-serif',
                  style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                  outlineWidth: 2,
                  verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                  pixelOffset: new Cesium.Cartesian2(0, -15),
                },
              });
              satelliteEntitiesRef.current.set(`sat-${trajectory.id}`, satEntity);
            }
          });
        }

        // Add formation satellites
        if (formationSatellites.length > 0) {
          console.log('[GlobeViewer] Adding formation satellites:', formationSatellites.length);
          formationSatellites.forEach((satellite, index) => {
            const color = satellite.color
              ? Cesium.Color.fromCssColorString(satellite.color)
              : satelliteColors[index % satelliteColors.length];

            if (satellite.positions.length > 0) {
              // Add trajectory
              const cartesianPositions = positionsToCartesian3(satellite.positions);
              viewer.entities.add({
                name: `${satellite.name} Trajectory`,
                polyline: {
                  positions: cartesianPositions,
                  width: 1,
                  material: color.withAlpha(0.5),
                },
              });

              // Add current position
              const currentPosIndex = Math.min(currentTime, satellite.positions.length - 1);
              const currentPos = satellite.positions[currentPosIndex];
              const satEntity = viewer.entities.add({
                name: satellite.name,
                position: new Cesium.Cartesian3(
                  currentPos[0] * 1000,
                  currentPos[1] * 1000,
                  currentPos[2] * 1000
                ),
                point: {
                  pixelSize: 10,
                  color: color,
                  outlineColor: Cesium.Color.BLACK,
                  outlineWidth: 1,
                },
                label: {
                  text: satellite.name,
                  font: '10px sans-serif',
                  style: Cesium.LabelStyle.FILL,
                  verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                  pixelOffset: new Cesium.Cartesian2(0, -12),
                },
              });
              satelliteEntitiesRef.current.set(`formation-${satellite.id}`, satEntity);
            }
          });
        }

        console.log('[GlobeViewer] 🎉 Cesium initialization complete!');
        console.log('[GlobeViewer] Setting isLoading to false...');
        setIsLoading(false);
        console.log('[GlobeViewer] ✅ isLoading set to false - globe should now be visible!');
      } catch (err) {
        console.error('[GlobeViewer] ❌ Failed to initialize Cesium:', err);
        console.error('[GlobeViewer] Error details:', err instanceof Error ? err.stack : err);
        setError(err instanceof Error ? err.message : 'Failed to initialize 3D viewer');
        setIsLoading(false);
      }
    };

    // Add a small delay to ensure DOM is ready
    console.log('[GlobeViewer] Setting up 100ms timer before initialization...');
    const timer = setTimeout(() => {
      console.log('[GlobeViewer] Timer fired, calling initCesium()...');
      initCesium();
    }, 100);

    return () => {
      console.log('[GlobeViewer] Cleanup function called');
      clearTimeout(timer);
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
        console.log('[GlobeViewer] Destroying Cesium Viewer...');
        viewerRef.current.destroy();
      }
    };
  }, [satellitePositions, gravityData, orbitTrajectories, formationSatellites, showOrbitPaths, showGroundTracks, currentTime, positionsToCartesian3, getGroundTrack, satelliteColors]);

  return (
    <div className="relative w-full h-screen">
      {/* Always render the viewer container so the ref is attached */}
      <div ref={viewerContainerRef} className="w-full h-full" />

      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-900 z-50">
          <div className="text-center">
            <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-500 mx-auto mb-4"></div>
            <p className="text-gray-400">Initializing Cesium...</p>
          </div>
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-900 z-50">
          <div className="text-center max-w-md">
            <div className="text-red-500 text-6xl mb-4">⚠️</div>
            <h2 className="text-xl font-bold text-white mb-2">Failed to Load 3D Viewer</h2>
            <p className="text-gray-400 mb-4">{error}</p>
            <p className="text-sm text-gray-500">
              Please check your Cesium Ion token configuration in .env.local
            </p>
          </div>
        </div>
      )}

      {/* Info panel */}
      {selectedPoint !== null && gravityData[selectedPoint] && (
        <div className="absolute top-4 right-4 bg-white p-4 rounded-lg shadow-lg">
          <h3 className="font-bold mb-2">Gravity Measurement</h3>
          <div className="text-sm space-y-1">
            <div>
              <span className="font-medium">Anomaly:</span>{' '}
              {gravityData[selectedPoint].anomaly.toFixed(2)} mGal
            </div>
            <div>
              <span className="font-medium">Position:</span>
              <div className="pl-4">
                X: {gravityData[selectedPoint].position[0].toFixed(2)} m<br />
                Y: {gravityData[selectedPoint].position[1].toFixed(2)} m<br />
                Z: {gravityData[selectedPoint].position[2].toFixed(2)} m
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
