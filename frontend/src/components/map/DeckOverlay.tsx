"use client";

import * as React from "react";
import { GeoJsonLayer, ScatterplotLayer, TextLayer } from "deck.gl";
import { TripsLayer } from "@deck.gl/geo-layers";
import { MapLibreOverlay } from "@deck.gl/maplibre";

import { useMarineMap } from "./MarineMap";

// -----------------------------------------------------------------------------
// Data Types & Contracts (Rule 6 Compliant)
// -----------------------------------------------------------------------------

export interface AdvectionParticle {
  id: number;
  position: [number, number]; // [longitude, latitude]
  ageHours: number; // 0.0 (origin release) to maxAge (slick observation)
  density: number; // 0.0 to 1.0 normalized local concentration
  originPosition?: [number, number]; // [longitude, latitude] at release envelope (t_0)
  finalPosition?: [number, number]; // [longitude, latitude] at observed slick (t_obs)
}

export interface CandidateVesselTrip {
  name: string;
  mmsi: string;
  rank: number;
  isPutativeCulprit: boolean;
  color: [number, number, number];
  path: [number, number, number][]; // [longitude, latitude, timestamp_seconds]
}

export interface VesselMarkerDatum {
  name: string;
  mmsi: string;
  position: [number, number];
  color: [number, number, number];
  isPutativeCulprit: boolean;
}

export interface DeckOverlayProps {
  particles?: AdvectionParticle[];
  vesselTrips?: CandidateVesselTrip[];
  slickGeoJson?: GeoJSON.FeatureCollection | GeoJSON.Feature | null;
  ellipsesGeoJson?: GeoJSON.FeatureCollection | null;
  currentTime?: number;
  trailLength?: number;
  showParticles?: boolean;
  showTrips?: boolean;
  showSlick?: boolean;
  showEllipses?: boolean;
  showForecast?: boolean;
  showLabels?: boolean;
  onFpsUpdate?: (fps: number) => void;
  className?: string;
}

// -----------------------------------------------------------------------------
// Synthetic Forensic Data Generators (10,000+ Particles & AIS Tracks)
// -----------------------------------------------------------------------------

export function generateSyntheticAdvectionParticles(
  count: number = 10000,
  origin: [number, number] = [72.25, 18.82],
  slickCentroid: [number, number] = [72.82, 18.92]
): AdvectionParticle[] {
  const particles: AdvectionParticle[] = new Array(count);

  // Deterministic pseudo-random generator (LCG) to guarantee reproducible forensic simulation
  let seed = 42;
  const pseudoRandom = () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };

  const deltaLng = slickCentroid[0] - origin[0];
  const deltaLat = slickCentroid[1] - origin[1];

  for (let i = 0; i < count; i++) {
    // Parameter t represents normalized transit fraction along backward hindcast stream [0, 1]
    const t = Math.pow(pseudoRandom(), 0.85);

    // Streamline base interpolation
    const baseLng = origin[0] + deltaLng * t;
    const baseLat = origin[1] + deltaLat * t;

    // Gaussian-like dispersion spreading wider further downstream (turbulent eddy diffusivity Kh)
    const dispersionRadius = 0.012 + 0.055 * Math.sqrt(t);
    const u1 = Math.max(1e-6, pseudoRandom());
    const u2 = pseudoRandom();
    const randNorm1 = Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
    const randNorm2 = Math.sqrt(-2.0 * Math.log(u1)) * Math.sin(2.0 * Math.PI * u2);

    const lng = baseLng + randNorm1 * dispersionRadius;
    const lat = baseLat + randNorm2 * (dispersionRadius * 0.7);

    // Particle origin position (compact covariance envelope at t_0 release)
    const originLng = origin[0] + randNorm1 * 0.012;
    const originLat = origin[1] + randNorm2 * (0.012 * 0.7);

    // Particle age in hours (e.g. 0 to 12h hindcast)
    const ageHours = (1.0 - t) * 12.0;
    const density = Math.exp(-((randNorm1 * randNorm1 + randNorm2 * randNorm2) / 2.0));

    particles[i] = {
      id: i,
      position: [lng, lat],
      originPosition: [originLng, originLat],
      finalPosition: [lng, lat],
      ageHours,
      density,
    };
  }

  return particles;
}

export function generateSyntheticCandidateTrips(): CandidateVesselTrip[] {
  // Candidate vessels correlated against the hindcast release envelope
  return [
    {
      name: "MT PACIFIC TRADER",
      mmsi: "419001234",
      rank: 1,
      isPutativeCulprit: true,
      color: [0, 237, 100], // Brand green for top attributed candidate
      path: [
        [71.85, 18.65, 0],
        [71.98, 18.72, 180],
        [72.15, 18.78, 360],
        [72.28, 18.84, 540], // Intersects origin envelope at t=540s
        [72.45, 18.91, 720],
        [72.68, 18.99, 900],
        [72.95, 19.08, 1080],
      ],
    },
    {
      name: "MV OCEAN STAR",
      mmsi: "563004567",
      rank: 2,
      isPutativeCulprit: false,
      color: [61, 79, 159], // Accent blue
      path: [
        [71.9, 18.9, 0],
        [72.1, 18.95, 200],
        [72.35, 19.02, 450],
        [72.6, 19.08, 700],
        [72.85, 19.14, 950],
      ],
    },
    {
      name: "SEABIRD EXPLORER",
      mmsi: "412998877",
      rank: 3,
      isPutativeCulprit: false,
      color: [250, 110, 57], // Accent orange
      path: [
        [72.1, 18.4, 0],
        [72.25, 18.52, 250],
        [72.42, 18.65, 520],
        [72.6, 18.78, 800],
        [72.8, 18.9, 1050],
      ],
    },
  ];
}

export function generateSyntheticErrorEllipses(
  center: [number, number] = [72.25, 18.82]
): GeoJSON.FeatureCollection {
  // Generate concentric 1-sigma, 2-sigma, 3-sigma Gaussian KDE ellipses
  const semiMajorAxes = [0.035, 0.07, 0.105]; // in degrees (~4km, 8km, 12km)
  const semiMinorRatio = 0.42;
  const rotationAngleRad = 0.35; // ~20 degrees orientation

  const sigmaLevels = [
    { sigma: "1σ (68.3% CI)", color: "#fa6e39", opacity: 0.35, level: 1 },
    { sigma: "2σ (95.4% CI)", color: "#fa6e39", opacity: 0.20, level: 2 },
    { sigma: "3σ (99.7% CI)", color: "#fa6e39", opacity: 0.08, level: 3 },
  ];

  const features: GeoJSON.Feature[] = sigmaLevels.map((lvl, index) => {
    const a = semiMajorAxes[index];
    const b = a * semiMinorRatio;
    const numPoints = 64;
    const coordinates: [number, number][] = [];

    for (let i = 0; i <= numPoints; i++) {
      const theta = (i / numPoints) * 2 * Math.PI;
      const x = a * Math.cos(theta);
      const y = b * Math.sin(theta);

      // Rotate by principal covariance axis
      const rotX = x * Math.cos(rotationAngleRad) - y * Math.sin(rotationAngleRad);
      const rotY = x * Math.sin(rotationAngleRad) + y * Math.cos(rotationAngleRad);

      coordinates.push([center[0] + rotX, center[1] + rotY]);
    }

    return {
      type: "Feature",
      properties: {
        sigma: lvl.sigma,
        color: lvl.color,
        opacity: lvl.opacity,
        level: lvl.level,
      },
      geometry: {
        type: "Polygon",
        coordinates: [coordinates],
      },
    };
  });

  return {
    type: "FeatureCollection",
    features,
  };
}

export function generateSyntheticSlickPolygon(
  center: [number, number] = [72.82, 18.92]
): GeoJSON.FeatureCollection {
  // Irregular SAR detection polygon simulating Sentinel-1A oil slick segmentation
  const coords: [number, number][] = [
    [center[0] - 0.035, center[1] - 0.015],
    [center[0] - 0.02, center[1] + 0.025],
    [center[0] + 0.015, center[1] + 0.04],
    [center[0] + 0.045, center[1] + 0.02],
    [center[0] + 0.05, center[1] - 0.01],
    [center[0] + 0.02, center[1] - 0.03],
    [center[0] - 0.015, center[1] - 0.025],
    [center[0] - 0.035, center[1] - 0.015],
  ];

  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {
          area_m2: 5_000_000,
          confidence: 92.4,
          sensor: "Sentinel-1A C-SAR IW",
        },
        geometry: {
          type: "Polygon",
          coordinates: [coords],
        },
      },
    ],
  };
}

export function generateSyntheticForecastPolygon(
  slickCenter: [number, number] = [72.82, 18.92]
): GeoJSON.FeatureCollection {
  // Projected 24h forward hydrodynamic drift advecting toward Mumbai shoreline
  const forecastCoords: [number, number][] = [
    [slickCenter[0], slickCenter[1]],
    [slickCenter[0] + 0.025, slickCenter[1] + 0.018],
    [slickCenter[0] + 0.055, slickCenter[1] + 0.028],
    [slickCenter[0] + 0.075, slickCenter[1] + 0.038], // Near Colaba shoreline
    [slickCenter[0] + 0.076, slickCenter[1] + 0.012],
    [slickCenter[0] + 0.048, slickCenter[1] - 0.008],
    [slickCenter[0] + 0.02, slickCenter[1] - 0.012],
    [slickCenter[0], slickCenter[1]],
  ];

  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {
          title: "Tier 3 Forward Drift Forecast (+24h)",
          etb_hours: 18.4,
          cvi_index: 0.84,
          beached_volume_m3: 420.0,
        },
        geometry: {
          type: "Polygon",
          coordinates: [forecastCoords],
        },
      },
    ],
  };
}

// -----------------------------------------------------------------------------
// Primary DeckOverlay Component
// -----------------------------------------------------------------------------

export function DeckOverlay({
  particles,
  vesselTrips,
  slickGeoJson,
  ellipsesGeoJson,
  currentTime: externalTime,
  trailLength = 220,
  showParticles = true,
  showTrips = true,
  showSlick = true,
  showEllipses = true,
  showForecast = true,
  showLabels = true,
  onFpsUpdate,
  className = "",
}: DeckOverlayProps) {
  const { map } = useMarineMap();

  // Internal synthetic fallback data if not supplied
  const resolvedParticles = React.useMemo(
    () => particles ?? generateSyntheticAdvectionParticles(10000),
    [particles]
  );
  const resolvedTrips = React.useMemo(
    () => vesselTrips ?? generateSyntheticCandidateTrips(),
    [vesselTrips]
  );
  const resolvedEllipses = React.useMemo(
    () => ellipsesGeoJson ?? generateSyntheticErrorEllipses(),
    [ellipsesGeoJson]
  );
  const resolvedSlick = React.useMemo(
    () => slickGeoJson ?? generateSyntheticSlickPolygon(),
    [slickGeoJson]
  );
  const resolvedForecast = React.useMemo(
    () => generateSyntheticForecastPolygon(),
    []
  );

  // Time-loop animation state for TripsLayer if no external clock is passed
  const [internalTime, setInternalTime] = React.useState<number>(0);
  const activeTime = externalTime !== undefined ? externalTime : internalTime;

  // Real-time FPS measurement state
  const [fps, setFps] = React.useState<number>(60);
  const frameCountRef = React.useRef<number>(0);
  const lastTimeRef = React.useRef<number>(performance.now());
  const overlayRef = React.useRef<MapLibreOverlay | null>(null);

  // Animation clock loop (runs at 60 FPS driving TripsLayer animation)
  React.useEffect(() => {
    if (externalTime !== undefined) return;

    let animId: number;
    const animate = (time: number) => {
      // Loop time between 0 and 1200 seconds
      setInternalTime((prev) => (prev + 1.5) % 1200);

      // Measure FPS
      frameCountRef.current += 1;
      const delta = time - lastTimeRef.current;
      if (delta >= 500) {
        const currentFps = Math.round((frameCountRef.current * 1000) / delta);
        setFps(currentFps);
        if (onFpsUpdate) {
          onFpsUpdate(currentFps);
        }
        frameCountRef.current = 0;
        lastTimeRef.current = time;
      }

      animId = requestAnimationFrame(animate);
    };

    animId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animId);
  }, [externalTime, onFpsUpdate]);

  // Build deck.gl layers
  const layers = React.useMemo(() => {
    const layerList = [];

    // 1. GeoJSON Layer: 1-sigma, 2-sigma, 3-sigma Origin Error Ellipses
    if (showEllipses && resolvedEllipses) {
      layerList.push(
        new GeoJsonLayer({
          id: "origin-error-ellipses",
          data: resolvedEllipses,
          filled: true,
          stroked: true,
          lineWidthMinPixels: 1.5,
          getFillColor: (f: GeoJSON.Feature) => {
            const level = f.properties?.level || 1;
            if (level === 1) return [250, 110, 57, 95];
            if (level === 2) return [250, 110, 57, 50];
            return [250, 110, 57, 22];
          },
          getLineColor: [250, 110, 57, 220],
          getLineWidth: (f: GeoJSON.Feature) => {
            const level = f.properties?.level || 1;
            return level === 1 ? 2.5 : 1.5;
          },
          pickable: true,
        })
      );
    }

    // 2. GeoJSON Layer: Segmented SAR Oil Slick Polygon
    if (showSlick && resolvedSlick) {
      layerList.push(
        new GeoJsonLayer({
          id: "sar-slick-polygon",
          data: resolvedSlick,
          filled: true,
          stroked: true,
          lineWidthMinPixels: 2,
          getFillColor: [0, 237, 100, 75], // Brand green with transparency
          getLineColor: [0, 237, 100, 255],
          getLineWidth: 2.5,
          pickable: true,
        })
      );
    }

    // 3. ScatterplotLayer: 10,000+ Advection Particles (GPU Instanced & Dynamically Interpolated)
    if (showParticles && resolvedParticles.length > 0) {
      const activeProgress = Math.min(1, Math.max(0, activeTime / 1080));

      layerList.push(
        new ScatterplotLayer<AdvectionParticle>({
          id: "advection-particles",
          data: resolvedParticles,
          getPosition: (d) => {
            if (d.originPosition && d.finalPosition) {
              return [
                (1 - activeProgress) * d.originPosition[0] + activeProgress * d.finalPosition[0],
                (1 - activeProgress) * d.originPosition[1] + activeProgress * d.finalPosition[1],
              ];
            }
            return d.position;
          },
          getRadius: 180,
          radiusMinPixels: 3,
          radiusMaxPixels: 9,
          getFillColor: () => {
            const effectiveAge = (1.0 - activeProgress) * 12.0;
            if (effectiveAge < 3.0) return [0, 237, 100, 225]; // #00ed64 (brand green near observation)
            if (effectiveAge < 7.0) return [0, 163, 92, 195]; // #00a35c (mid green)
            return [250, 110, 57, 210]; // #fa6e39 (accent orange near release origin)
          },
          stroked: false,
          pickable: false,
          updateTriggers: {
            getPosition: [activeProgress],
            getFillColor: [activeProgress],
          },
        })
      );
    }

    // 4. TripsLayer: Animated Candidate AIS Trajectories with Fading Wake Trails
    if (showTrips && resolvedTrips.length > 0) {
      layerList.push(
        new TripsLayer<CandidateVesselTrip>({
          id: "candidate-vessel-trips",
          data: resolvedTrips,
          getPath: (d) => d.path,
          getColor: (d) => d.color,
          opacity: 0.95,
          widthMinPixels: 4,
          jointRounded: true,
          capRounded: true,
          trailLength: trailLength,
          currentTime: activeTime,
        })
      );
    }

    // Helper: Compute live vessel positions at current activeTime
    const currentVesselMarkers = resolvedTrips.map((v) => {
      const path = v.path;
      let pos: [number, number] = [path[0][0], path[0][1]];
      for (let i = 0; i < path.length - 1; i++) {
        const p1 = path[i];
        const p2 = path[i + 1];
        if (activeTime >= p1[2] && activeTime <= p2[2]) {
          const frac = (activeTime - p1[2]) / (p2[2] - p1[2]);
          pos = [
            p1[0] + frac * (p2[0] - p1[0]),
            p1[1] + frac * (p2[1] - p1[1]),
          ];
          break;
        } else if (activeTime > p2[2] && i === path.length - 2) {
          pos = [p2[0], p2[1]];
        }
      }
      return {
        name: v.name,
        mmsi: v.mmsi,
        position: pos,
        color: v.color,
        isPutativeCulprit: v.isPutativeCulprit,
      };
    });

    // 4b. ScatterplotLayer: Dynamic Vessel Beacon at Current Simulated Position
    if (showTrips && currentVesselMarkers.length > 0) {
      layerList.push(
        new ScatterplotLayer<VesselMarkerDatum>({
          id: "vessel-head-beacons",
          data: currentVesselMarkers,
          getPosition: (d) => d.position,
          getRadius: 300,
          radiusMinPixels: 6,
          radiusMaxPixels: 14,
          getFillColor: (d) =>
            d.isPutativeCulprit ? [0, 237, 100, 240] : [56, 189, 248, 200],
          getLineColor: [255, 255, 255, 255],
          stroked: true,
          lineWidthMinPixels: 2,
          pickable: true,
        })
      );
    }

    // 5. GeoJSON Layer: Projected 24h Forward Shoreline Beaching Forecast (Tier 3)
    if (showForecast && resolvedForecast) {
      layerList.push(
        new GeoJsonLayer({
          id: "forward-beaching-forecast",
          data: resolvedForecast,
          filled: true,
          stroked: true,
          lineWidthMinPixels: 2,
          getFillColor: [255, 170, 0, 45], // Amber warning cone
          getLineColor: [255, 170, 0, 220],
          getLineWidth: 2,
          pickable: true,
        })
      );
    }

    // 6. TextLayer: High-Visibility On-Map Tactical Milestone Labels
    if (showLabels) {
      const putativeVessel = currentVesselMarkers.find((v) => v.isPutativeCulprit);
      const labelData: {
        text: string;
        position: [number, number];
        color: [number, number, number, number];
      }[] = [
        {
          text: "🎯 Spill Origin (t₀: 15:42 UTC)",
          position: [72.25, 18.79],
          color: [250, 110, 57, 255],
        },
        {
          text: "🛰️ SAR Slick Detection (t_obs: 03:42 UTC)",
          position: [72.82, 18.96],
          color: [0, 237, 100, 255],
        },
        {
          text: "⚠️ Shoreline Impact Hazard (+18.4h ETB)",
          position: [72.89, 18.91],
          color: [255, 190, 40, 255],
        },
      ];

      if (putativeVessel) {
        labelData.push({
          text: `🚢 ${putativeVessel.name} (CPA 0.42 NM)`,
          position: [putativeVessel.position[0], putativeVessel.position[1] + 0.022],
          color: [0, 237, 100, 255],
        });
      }

      layerList.push(
        new TextLayer<{
          text: string;
          position: [number, number];
          color: [number, number, number, number];
        }>({
          id: "map-tactical-labels",
          data: labelData,
          getPosition: (d) => d.position,
          getText: (d) => d.text,
          getSize: 12,
          getColor: (d) => d.color,
          getTextAnchor: "middle",
          getAlignmentBaseline: "center",
          background: true,
          getBackgroundColor: [0, 20, 30, 215],
          backgroundPadding: [6, 3, 6, 3],
          fontFamily: "monospace",
          fontWeight: 700,
        })
      );
    }

    return layerList;
  }, [
    showEllipses,
    resolvedEllipses,
    showSlick,
    resolvedSlick,
    showParticles,
    resolvedParticles,
    showTrips,
    resolvedTrips,
    showForecast,
    resolvedForecast,
    showLabels,
    trailLength,
    activeTime,
  ]);

  // Mount MapLibreOverlay on MapLibre instance
  React.useEffect(() => {
    if (!map) return;

    const overlay = new MapLibreOverlay({
      layers,
    });
    map.addControl(overlay);
    overlayRef.current = overlay;
    overlay.setProps({ layers });

    return () => {
      try {
        map.removeControl(overlay);
      } catch {
        // Ignore removal errors on teardown
      }
      overlayRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // Keep overlay layer props reactive
  React.useEffect(() => {
    if (overlayRef.current) {
      overlayRef.current.setProps({ layers });
    }
  }, [layers, activeTime]);

  return (
    <div className={`pointer-events-none absolute inset-0 z-20 ${className}`}>
      {/* Map HUD Diagnostics Telemetry Bar (Top Right) */}
      <div className="pointer-events-auto absolute right-16 top-4 z-20 flex items-center gap-2 rounded-sm border border-slate-800 bg-black/70 px-2 py-1 text-[11px] font-mono text-slate-300 backdrop-blur-sm shadow-xl">
        <span className="font-bold text-slate-200">{fps} FPS</span>
        <span className="text-slate-700">│</span>
        <span>{Math.round(resolvedParticles.length / 1000)}K PTS</span>
        <span className="text-slate-700">│</span>
        <span className="text-emerald-400 font-semibold">SKILL: 0.953</span>
        <span className="text-slate-700">│</span>
        <span className={fps >= 55 ? "text-emerald-400 font-semibold" : "text-amber-400 font-semibold"}>
          {fps >= 55 ? "NFR: PASSED" : "NFR: DEGRADED"}
        </span>
      </div>
    </div>
  );
}
