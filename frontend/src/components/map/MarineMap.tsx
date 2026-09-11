"use client";

import * as React from "react";
import { Map, NavigationControl, FullscreenControl, ScaleControl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { createDarkMarineMapStyle } from "./map-style";
import { LayerControlPanel, type LayerVisibilityState } from "./LayerControlPanel";
import { Button } from "@/components/ui/button";
import { Compass, Maximize2 } from "lucide-react";

export interface ViewportState {
  longitude: number;
  latitude: number;
  zoom: number;
  bearing: number;
  pitch: number;
}

export interface MapContextType {
  map: Map | null;
  viewport: ViewportState;
}

export const MapContext = React.createContext<MapContextType>({
  map: null,
  viewport: { longitude: 72.8258, latitude: 18.925, zoom: 8.5, bearing: 0, pitch: 25 },
});

export function useMarineMap(): MapContextType {
  return React.useContext(MapContext);
}

export interface MarineMapProps {
  initialCenter?: [number, number]; // [lng, lat]
  initialZoom?: number;
  boundingBox?: [number, number, number, number] | null; // [minLng, minLat, maxLng, maxLat]
  onViewportChange?: (viewport: ViewportState) => void;
  className?: string;
  children?: React.ReactNode;
}

export function MarineMap({
  initialCenter = [72.535, 18.87], // Offshore Mumbai High incident center
  initialZoom = 9.2,
  boundingBox = null,
  onViewportChange,
  className = "w-full h-[600px]",
  children,
}: MarineMapProps) {
  const mapContainerRef = React.useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = React.useRef<Map | null>(null);
  const [mapInstance, setMapInstance] = React.useState<Map | null>(null);
  const [viewport, setViewport] = React.useState<ViewportState>({
    longitude: initialCenter[0],
    latitude: initialCenter[1],
    zoom: initialZoom,
    bearing: 0,
    pitch: 25,
  });

  const [mouseCoords, setMouseCoords] = React.useState<{ lng: number; lat: number } | null>(null);
  const [currentZoom, setCurrentZoom] = React.useState<number>(initialZoom);
  const [currentBearing, setCurrentBearing] = React.useState<number>(0);

  const [layers, setLayers] = React.useState<LayerVisibilityState>({
    bathymetry: true,
    eez: true,
    shippingLanes: true,
    mpa: true,
  });

  // Initialize MapLibre GL instance
  React.useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const style = createDarkMarineMapStyle();

    const map = new Map({
      container: mapContainerRef.current,
      style: style,
      center: initialCenter,
      zoom: initialZoom,
      pitch: 25,
      bearing: 0,
      attributionControl: false,
    });

    mapInstanceRef.current = map;
    setMapInstance(map);
    (window as unknown as Record<string, unknown>).__mapInstance = map;

    map.on("error", (e) => {
      console.warn("[MarineMap Error]", e);
    });

    // 1. Navigation Control (Zoom, 3D Pitch, Bearing)
    const navControl = new NavigationControl({
      showCompass: true,
      showZoom: true,
      visualizePitch: true,
    });
    map.addControl(navControl, "top-right");

    // 2. Fullscreen Control
    const fullscreenControl = new FullscreenControl();
    map.addControl(fullscreenControl, "top-right");

    // 3. Dual Scale Indicators: Nautical Miles (NM) & Metric (km)
    const nauticalScale = new ScaleControl({
      maxWidth: 120,
      unit: "nautical",
    });
    map.addControl(nauticalScale, "bottom-left");

    const metricScale = new ScaleControl({
      maxWidth: 120,
      unit: "metric",
    });
    map.addControl(metricScale, "bottom-left");

    // Event listeners
    map.on("mousemove", (e) => {
      setMouseCoords({
        lng: Number(e.lngLat.lng.toFixed(4)),
        lat: Number(e.lngLat.lat.toFixed(4)),
      });
    });

    map.on("move", () => {
      const center = map.getCenter();
      const zoom = map.getZoom();
      const bearing = map.getBearing();
      const pitch = map.getPitch();

      const newViewport = {
        longitude: center.lng,
        latitude: center.lat,
        zoom,
        bearing,
        pitch,
      };

      setCurrentZoom(Number(zoom.toFixed(1)));
      setCurrentBearing(Math.round(bearing));
      setViewport(newViewport);

      if (onViewportChange) {
        onViewportChange(newViewport);
      }
    });

    // Auto-fit bounding box on initial load if provided
    map.on("load", () => {
      if (boundingBox) {
        map.fitBounds(
          [
            [boundingBox[0], boundingBox[1]],
            [boundingBox[2], boundingBox[3]],
          ],
          { padding: 50, duration: 800 }
        );
      }
    });

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run once on mount

  // Sync bounding box updates only when coordinates actually change
  const boundingBoxKey = boundingBox ? boundingBox.join(",") : null;
  const lastFitBoundsKeyRef = React.useRef<string | null>(null);

  React.useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !boundingBox || !boundingBoxKey) return;
    if (lastFitBoundsKeyRef.current === boundingBoxKey) return;
    lastFitBoundsKeyRef.current = boundingBoxKey;

    map.fitBounds(
      [
        [boundingBox[0], boundingBox[1]],
        [boundingBox[2], boundingBox[3]],
      ],
      { padding: 50, duration: 800 }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boundingBoxKey]);

  // Sync layer visibility state
  const handleToggleLayer = (layerKey: keyof LayerVisibilityState) => {
    const nextState = !layers[layerKey];
    setLayers((prev) => ({ ...prev, [layerKey]: nextState }));

    const map = mapInstanceRef.current;
    if (!map) return;

    const visibilityValue = nextState ? "visible" : "none";

    switch (layerKey) {
      case "bathymetry":
        if (map.getLayer("bathymetry-lines")) {
          map.setLayoutProperty("bathymetry-lines", "visibility", visibilityValue);
        }
        break;
      case "eez":
        if (map.getLayer("eez-lines")) {
          map.setLayoutProperty("eez-lines", "visibility", visibilityValue);
        }
        break;
      case "shippingLanes":
        if (map.getLayer("shipping-lanes-fill")) {
          map.setLayoutProperty("shipping-lanes-fill", "visibility", visibilityValue);
        }
        if (map.getLayer("shipping-lanes-line")) {
          map.setLayoutProperty("shipping-lanes-line", "visibility", visibilityValue);
        }
        break;
      case "mpa":
        if (map.getLayer("mpa-fill")) {
          map.setLayoutProperty("mpa-fill", "visibility", visibilityValue);
        }
        if (map.getLayer("mpa-border")) {
          map.setLayoutProperty("mpa-border", "visibility", visibilityValue);
        }
        break;
    }
  };

  // Reset bearing to North
  const handleResetBearing = () => {
    mapInstanceRef.current?.resetNorthPitch({ duration: 800 });
  };

  // Fit to incident envelope
  const handleFitIncidentEnvelope = () => {
    mapInstanceRef.current?.flyTo({
      center: initialCenter,
      zoom: initialZoom,
      pitch: 25,
      bearing: 0,
      duration: 1200,
    });
  };

  return (
    <MapContext.Provider value={{ map: mapInstance, viewport }}>
      <div className={`relative overflow-hidden rounded-sm border border-[#1F2937] bg-[#0B0F14] ${className}`}>
        {/* MapLibre Canvas Host Container */}
        <div ref={mapContainerRef} className="h-full w-full" />

        {/* Floating Layer Control Switcher (Top Left) */}
        <div className="absolute left-4 top-4 z-10 max-w-xs">
          <LayerControlPanel layers={layers} onToggleLayer={handleToggleLayer} />
        </div>

        {/* Floating Quick Action Buttons (Top Right, below standard map controls) */}
        <div className="absolute right-4 top-28 z-10 flex flex-col gap-1.5">
          <button
            type="button"
            onClick={handleResetBearing}
            title="Reset Heading to True North"
            className="h-7 w-7 flex items-center justify-center rounded-sm bg-[#111720]/90 border border-slate-800 text-slate-300 hover:text-white hover:border-slate-600 backdrop-blur-sm shadow"
          >
            <Compass className="h-3.5 w-3.5 text-emerald-400" />
          </button>
          <button
            type="button"
            onClick={handleFitIncidentEnvelope}
            title="Fit to Incident Envelope"
            className="h-7 w-7 flex items-center justify-center rounded-sm bg-[#111720]/90 border border-slate-800 text-slate-300 hover:text-white hover:border-slate-600 backdrop-blur-sm shadow"
          >
            <Maximize2 className="h-3.5 w-3.5 text-slate-200" />
          </button>
        </div>

        {/* Live Coordinate & Telemetry HUD Bar (Bottom Right) */}
        <div className="absolute bottom-4 right-4 z-10 rounded-sm border border-slate-800 bg-black/70 px-2 py-1 font-mono text-[11px] text-slate-300 shadow-xl backdrop-blur-sm tabular-nums">
          <div className="flex items-center gap-2">
            <span>
              {mouseCoords
                ? `${mouseCoords.lat >= 0 ? `${mouseCoords.lat.toFixed(4)}° N` : `${Math.abs(mouseCoords.lat).toFixed(4)}° S`}, ${mouseCoords.lng >= 0 ? `${mouseCoords.lng.toFixed(4)}° E` : `${Math.abs(mouseCoords.lng).toFixed(4)}° W`}`
                : `${initialCenter[1].toFixed(4)}° N, ${initialCenter[0].toFixed(4)}° E`}
            </span>
            <span className="text-slate-700">│</span>
            <span>Zoom: {currentZoom}</span>
            <span className="text-slate-700">│</span>
            <span>HDG: {currentBearing}°</span>
          </div>
        </div>

        {/* Optional Child Overlays (e.g. deck.gl canvas in TASK-042) */}
        {children}
      </div>
    </MapContext.Provider>
  );
}
