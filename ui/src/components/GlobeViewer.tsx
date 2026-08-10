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

// Stable empty defaults: inline [] defaults are new arrays on every
// render and sit in the init effect's dependency list, which tore the
// whole Cesium viewer down and rebuilt it on every parent re-render
// (leaking WebGL contexts).
const EMPTY_SAT_POSITIONS: SatellitePosition[] = [];
const EMPTY_GRAVITY: GravityMeasurement[] = [];
const EMPTY_TRAJECTORIES: OrbitTrajectory[] = [];
const EMPTY_FORMATION: FormationSatellite[] = [];
const SATELLITE_COLORS = [
  Cesium.Color.YELLOW,
  Cesium.Color.CYAN,
  Cesium.Color.MAGENTA,
  Cesium.Color.LIME,
  Cesium.Color.ORANGE,
];

export default function GlobeViewer({
  satellitePositions = EMPTY_SAT_POSITIONS,
  gravityData = EMPTY_GRAVITY,
  showGrid = false,
  orbitTrajectories = EMPTY_TRAJECTORIES,
  formationSatellites = EMPTY_FORMATION,
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
  const [clickedLocation, setClickedLocation] = useState<{
    latitude: number;
    longitude: number;
    altitude: number;
    cartesian: { x: number; y: number; z: number };
  } | null>(null);

  // Color palette for satellites (module-scope constant)
  const satelliteColors = SATELLITE_COLORS;

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
        // Never create a viewer into a zero-size container - Cesium
        // throws 'Expected width to be greater than 0' and rendering
        // stops for good.
        const el = viewerContainerRef.current;
        if (!el || el.clientWidth === 0 || el.clientHeight === 0) {
          console.warn('[GlobeViewer] container has no size yet, retrying…');
          setTimeout(initCesium, 200);
          return;
        }
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

        // Create the Viewer with minimal configuration to avoid Ion token issues
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
          baseLayer: false, // Disable default imagery initially
          terrain: undefined, // Disable terrain
        });

        // Add high-resolution imagery layer
        try {
          // Try ESRI World Imagery first (high quality satellite imagery)
          const esriProvider = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
            'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
          );
          viewer.imageryLayers.addImageryProvider(esriProvider);
          console.log('[GlobeViewer] Using ESRI World Imagery (high resolution)');

          // Add street/place labels overlay on top of satellite imagery
          try {
            const labelsProvider = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
              'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer'
            );
            viewer.imageryLayers.addImageryProvider(labelsProvider);
            console.log('[GlobeViewer] Added street labels overlay');
          } catch (labelError) {
            console.warn('[GlobeViewer] Could not add labels overlay');
          }
        } catch (esriError) {
          console.warn('[GlobeViewer] ESRI failed, trying OpenStreetMap...');
          try {
            // Fallback to OpenStreetMap
            const osmProvider = new Cesium.OpenStreetMapImageryProvider({
              url: 'https://tile.openstreetmap.org/'
            });
            viewer.imageryLayers.addImageryProvider(osmProvider);
            console.log('[GlobeViewer] Using OpenStreetMap');
          } catch (osmError) {
            console.warn('[GlobeViewer] OSM failed, using NaturalEarthII offline...');
            try {
              // Final fallback to offline NaturalEarthII
              const naturalEarthProvider = await Cesium.TileMapServiceImageryProvider.fromUrl(
                Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII")
              );
              viewer.imageryLayers.addImageryProvider(naturalEarthProvider);
            } catch (neError) {
              // Ultimate fallback - solid color
              viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#1e3a5f');
            }
          }
        }

        // Add 3D buildings from OpenStreetMap
        try {
          const osmBuildings = await Cesium.createOsmBuildingsAsync();
          viewer.scene.primitives.add(osmBuildings);
          console.log('[GlobeViewer] Added 3D OSM Buildings');
        } catch (buildingError) {
          console.warn('[GlobeViewer] Could not add 3D buildings:', buildingError);
        }

        // Enable depth testing for better 3D rendering
        viewer.scene.globe.depthTestAgainstTerrain = true;

        console.log('[GlobeViewer] ✅ Cesium Viewer created successfully!');
        console.log('[GlobeViewer] Viewer object:', viewer);

        viewerRef.current = viewer;

        // Frame the full Earth regardless of container size
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(-30.0, 20.0, 1.2e7),
        });

        // Add click handler for location pinpointing
        const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
        handler.setInputAction((click: { position: Cesium.Cartesian2 }) => {
          const cartesian = viewer.camera.pickEllipsoid(
            click.position,
            viewer.scene.globe.ellipsoid
          );

          if (cartesian) {
            const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
            const longitude = Cesium.Math.toDegrees(cartographic.longitude);
            const latitude = Cesium.Math.toDegrees(cartographic.latitude);
            const altitude = cartographic.height;

            setClickedLocation({
              latitude,
              longitude,
              altitude,
              cartesian: { x: cartesian.x, y: cartesian.y, z: cartesian.z },
            });

            // Add or update a marker at the clicked location
            const existingMarker = viewer.entities.getById('clickedLocationMarker');
            if (existingMarker) {
              viewer.entities.remove(existingMarker);
            }

            viewer.entities.add({
              id: 'clickedLocationMarker',
              name: 'Selected Location',
              position: cartesian,
              point: {
                pixelSize: 14,
                color: Cesium.Color.RED,
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 2,
              },
              label: {
                text: `${latitude.toFixed(4)}°, ${longitude.toFixed(4)}°`,
                font: '12px sans-serif',
                style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                outlineWidth: 2,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                pixelOffset: new Cesium.Cartesian2(0, -20),
                fillColor: Cesium.Color.WHITE,
                outlineColor: Cesium.Color.BLACK,
              },
            });
          }
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

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
  }, [satellitePositions, gravityData, orbitTrajectories, formationSatellites, showOrbitPaths, showGroundTracks, currentTime, positionsToCartesian3, getGroundTrack]);

  return (
    // Fill the parent container — pages decide the size. (This was
    // h-screen, which clipped to half a globe inside fixed-height
    // cards.)
    <div className="relative w-full h-full min-h-[300px]">
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

      {/* Location Info Panel */}
      {clickedLocation && (
        <div className="absolute top-4 left-4 bg-gray-800/95 backdrop-blur-sm p-4 rounded-lg shadow-xl border border-gray-700 min-w-[280px]">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-bold text-white flex items-center gap-2">
              <span className="text-red-500">📍</span> Selected Location
            </h3>
            <button
              onClick={() => setClickedLocation(null)}
              className="text-gray-400 hover:text-white text-sm"
            >
              ✕
            </button>
          </div>
          <div className="text-sm space-y-2 text-gray-300">
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-gray-900/50 p-2 rounded">
                <div className="text-xs text-gray-500">Latitude</div>
                <div className="font-mono text-green-400">
                  {clickedLocation.latitude.toFixed(6)}°
                </div>
              </div>
              <div className="bg-gray-900/50 p-2 rounded">
                <div className="text-xs text-gray-500">Longitude</div>
                <div className="font-mono text-blue-400">
                  {clickedLocation.longitude.toFixed(6)}°
                </div>
              </div>
            </div>
            <div className="bg-gray-900/50 p-2 rounded">
              <div className="text-xs text-gray-500">ECEF Cartesian (meters)</div>
              <div className="font-mono text-xs text-yellow-400 mt-1">
                X: {clickedLocation.cartesian.x.toFixed(2)}<br />
                Y: {clickedLocation.cartesian.y.toFixed(2)}<br />
                Z: {clickedLocation.cartesian.z.toFixed(2)}
              </div>
            </div>
            <div className="text-xs text-gray-500 mt-2">
              Click anywhere on the globe to select a new location
            </div>
          </div>
        </div>
      )}

      {/* Gravity Measurement Info panel */}
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

      {/* Instructions overlay when no location selected */}
      {!clickedLocation && !isLoading && !error && (
        <div className="absolute bottom-4 left-4 bg-gray-800/80 backdrop-blur-sm px-4 py-2 rounded-lg border border-gray-700">
          <p className="text-sm text-gray-300">
            <span className="text-blue-400">Click</span> on the globe to pinpoint a location
          </p>
        </div>
      )}
    </div>
  );
}
