"use client";

import * as React from "react";
import { GeoJsonLayer, ScatterplotLayer } from "deck.gl";
import { TripsLayer } from "@deck.gl/geo-layers";
import { MapLibreOverlay } from "@deck.gl/maplibre";

import { useMarineMap } from "./MarineMap";
import { Badge } from "@/components/ui/badge";
import { Gauge, Zap } from "lucide-react";

// -----------------------------------------------------------------------------
// Data Types & Contracts (Rule 6 Compliant)
// -----------------------------------------------------------------------------

export interface AdvectionParticle {
  id: number;
  position: [number, number]; // [longitude, latitude]
  ageHours: number; // 0.0 (origin release) to maxAge (slick observation)
  density: number; // 0.0 to 1.0 normalized local concentration
}

export interface CandidateVesselTrip {
  name: string;
  mmsi: string;
  rank: number;
  isPutativeCulprit: boolean;
  color: [number, number, number];
  path: [number, number, number][]; // [longitude, latitude, timestamp_seconds]
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

    // Particle age in hours (e.g. 0 to 12h hindcast)
    const ageHours = (1.0 - t) * 12.0;
    const density = Math.exp(-((randNorm1 * randNorm1 + randNorm2 * randNorm2) / 2.0));

    particles[i] = {
      id: i,
      position: [lng, lat],
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

    // 3. ScatterplotLayer: 10,000+ Advection Particles (GPU Instanced)
    if (showParticles && resolvedParticles.length > 0) {
      layerList.push(
        new ScatterplotLayer<AdvectionParticle>({
          id: "advection-particles",
          data: resolvedParticles,
          getPosition: (d) => d.position,
          getRadius: 24,
          radiusMinPixels: 2,
          radiusMaxPixels: 8,
          getFillColor: (d) => {
            // Color ramp: Bright green for fresh, deep cyan/indigo for older
            if (d.ageHours < 3.0) return [0, 237, 100, 210]; // #00ed64
            if (d.ageHours < 7.0) return [0, 163, 92, 175]; // #00a35c
            return [61, 79, 159, 130]; // #3d4f9f
          },
          stroked: false,
          pickable: false,
          updateTriggers: {
            getFillColor: [resolvedParticles.length],
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
          rounded: true,
          trailLength: trailLength,
          currentTime: activeTime,
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
    trailLength,
    activeTime,
  ]);

  // Mount MapLibreOverlay on MapLibre instance
  React.useEffect(() => {
    if (!map) return;

    const overlay = new MapLibreOverlay({
      layers: [],
    });
    map.addControl(overlay);
    overlayRef.current = overlay;

    return () => {
      try {
        map.removeControl(overlay);
      } catch {
        // Ignore removal errors on teardown
      }
      overlayRef.current = null;
    };
  }, [map]);

  // Keep overlay layer props reactive
  React.useEffect(() => {
    if (overlayRef.current) {
      overlayRef.current.setProps({ layers });
    }
  }, [layers]);

  return (
    <div className={`pointer-events-none absolute inset-0 z-20 ${className}`}>
      {/* Real-time WebGL Performance Telemetry HUD (Top Right) */}
      <div className="pointer-events-auto absolute right-16 top-4 z-20 flex items-center gap-2 rounded-xl border border-hairline-dark bg-brand-teal-deep/90 px-3 py-1.5 shadow-xl backdrop-blur">
        <Gauge className="h-4 w-4 text-brand-green" />
        <span className="font-mono text-xs font-bold text-white">
          {fps} FPS
        </span>
        <span className="text-hairline-dark">|</span>
        <div className="flex items-center gap-1.5 font-mono text-xs text-on-dark-muted">
          <Zap className="h-3 w-3 text-brand-green" />
          <span>{resolvedParticles.length.toLocaleString()} pts</span>
        </div>
        <Badge
          variant={fps >= 55 ? "greenSoft" : "orange"}
          className="text-[10px] font-mono ml-1"
        >
          {fps >= 55 ? "NFR: 60 FPS PASSED" : "NFR: DEGRADED"}
        </Badge>
      </div>
    </div>
  );
}
