/**
 * AEGIS-Marine: Dark Nautical Cartography Style Specification (TASK-041)
 * Adheres strictly to DESIGN.md palette (#001e2b deep ocean canvas, subtle bathymetry,
 * UNCLOS EEZ limits, IMO TSS shipping lanes, and marine protected areas).
 */

import type { StyleSpecification } from "maplibre-gl";

// -----------------------------------------------------------------------------
// Baseline Arabian Sea / Mumbai High Geospatial Vector Overlays (GeoJSON)
// -----------------------------------------------------------------------------

export const BATHYMETRY_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { depth: -50, label: "50m Contour" },
      geometry: {
        type: "LineString",
        coordinates: [
          [72.5, 18.2],
          [72.6, 18.6],
          [72.7, 19.0],
          [72.65, 19.4],
          [72.5, 19.8],
        ],
      },
    },
    {
      type: "Feature",
      properties: { depth: -100, label: "100m Contour" },
      geometry: {
        type: "LineString",
        coordinates: [
          [72.1, 18.0],
          [72.2, 18.5],
          [72.3, 19.0],
          [72.2, 19.5],
          [72.0, 20.0],
        ],
      },
    },
    {
      type: "Feature",
      properties: { depth: -200, label: "200m Shelf Break" },
      geometry: {
        type: "LineString",
        coordinates: [
          [71.6, 17.8],
          [71.75, 18.4],
          [71.85, 19.0],
          [71.7, 19.6],
          [71.5, 20.2],
        ],
      },
    },
    {
      type: "Feature",
      properties: { depth: -500, label: "500m Slope" },
      geometry: {
        type: "LineString",
        coordinates: [
          [71.1, 17.5],
          [71.25, 18.3],
          [71.35, 19.0],
          [71.2, 19.7],
          [71.0, 20.4],
        ],
      },
    },
    {
      type: "Feature",
      properties: { depth: -1000, label: "1000m Abyssal" },
      geometry: {
        type: "LineString",
        coordinates: [
          [70.5, 17.2],
          [70.7, 18.1],
          [70.8, 19.0],
          [70.65, 19.9],
          [70.4, 20.6],
        ],
      },
    },
  ],
};

export const EEZ_BOUNDARIES_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Indian EEZ Western Limit (UNCLOS 200NM)", sovereignty: "India" },
      geometry: {
        type: "LineString",
        coordinates: [
          [68.8, 17.0],
          [69.2, 18.0],
          [69.6, 19.0],
          [69.4, 20.0],
          [68.9, 21.0],
        ],
      },
    },
  ],
};

export const SHIPPING_LANES_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Mumbai High TSS Inbound Corridor", type: "TSS_LANE" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [72.2, 18.7],
            [72.5, 18.8],
            [72.6, 18.9],
            [72.3, 18.8],
            [72.2, 18.7],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "Mumbai High TSS Outbound Corridor", type: "TSS_LANE" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [72.2, 18.95],
            [72.5, 19.05],
            [72.6, 19.15],
            [72.3, 19.05],
            [72.2, 18.95],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: { name: "International Persian Gulf - Malacca Transit Lane", type: "TRANSIT_ROUTE" },
      geometry: {
        type: "LineString",
        coordinates: [
          [69.0, 18.0],
          [71.0, 18.4],
          [72.4, 18.8],
          [73.5, 17.5],
          [75.0, 15.0],
        ],
      },
    },
  ],
};

export const MARINE_PROTECTED_AREAS_GEOJSON: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: {
        name: "Malvan Marine Sanctuary & Coastal Conservation Zone",
        designation: "Category IV Protected Area",
        restriction: "Zero Bilge / Oily Ballast Discharge Zone",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [73.4, 16.0],
            [73.6, 16.0],
            [73.6, 16.2],
            [73.4, 16.2],
            [73.4, 16.0],
          ],
        ],
      },
    },
  ],
};

// -----------------------------------------------------------------------------
// MapLibre GL Style Specification (Version 8)
// -----------------------------------------------------------------------------

export function createDarkMarineMapStyle(): StyleSpecification {
  const cartoKey =
    typeof process !== "undefined"
      ? process.env?.NEXT_PUBLIC_CARTO_API_KEY
      : undefined;

  // When no CARTO key is configured, default to ESRI World Dark Gray Canvas:
  // completely free, high-performance, and watermark-free for nautical and marine operations.
  const baseTiles = cartoKey
    ? [
        `https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png?api_key=${cartoKey}`,
        `https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png?api_key=${cartoKey}`,
        `https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png?api_key=${cartoKey}`,
        `https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png?api_key=${cartoKey}`,
      ]
    : [
        "https://services.arcgisonline.com/arcgis/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      ];

  const attribution = cartoKey
    ? '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
    : 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ';

  return {
    version: 8,
    name: "AEGIS Dark Nautical Marine",
    sources: {
      // Global dark nautical base raster tiles
      "carto-dark": {
        type: "raster",
        tiles: baseTiles,
        tileSize: 256,
        attribution,
      },
      // Nautical reference labels layer (ESRI Dark Gray Reference)
      "esri-reference": {
        type: "raster",
        tiles: [
          "https://services.arcgisonline.com/arcgis/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
        ],
        tileSize: 256,
      },
      // Bathymetry depth contours
      "bathymetry-source": {
        type: "geojson",
        data: BATHYMETRY_GEOJSON,
      },
      // UNCLOS EEZ Boundaries
      "eez-source": {
        type: "geojson",
        data: EEZ_BOUNDARIES_GEOJSON,
      },
      // IMO Shipping Lanes (TSS)
      "shipping-lanes-source": {
        type: "geojson",
        data: SHIPPING_LANES_GEOJSON,
      },
      // Marine Protected Areas (MPA)
      "mpa-source": {
        type: "geojson",
        data: MARINE_PROTECTED_AREAS_GEOJSON,
      },
    },
    layers: [
      // 1. Base Ocean Canvas (#001e2b)
      {
        id: "ocean-canvas",
        type: "background",
        paint: {
          "background-color": "#001e2b",
        },
      },
      // 2. Global Dark Land / Water Tiles
      {
        id: "carto-dark-tiles",
        type: "raster",
        source: "carto-dark",
        paint: {
          "raster-opacity": 0.85,
          "raster-contrast": 0.1,
          "raster-brightness-min": 0.05,
          "raster-brightness-max": 0.95,
        },
      },
      // 3. Nautical Reference Labels
      {
        id: "esri-reference-tiles",
        type: "raster",
        source: "esri-reference",
        paint: {
          "raster-opacity": cartoKey ? 0 : 0.8,
        },
      },
      // 3. Bathymetry Contours
      {
        id: "bathymetry-lines",
        type: "line",
        source: "bathymetry-source",
        layout: {
          "line-join": "round",
          "line-cap": "round",
          visibility: "visible",
        },
        paint: {
          "line-color": "#00a35c",
          "line-width": 1.2,
          "line-opacity": 0.45,
          "line-dasharray": [4, 3],
        },
      },
      // 4. Exclusive Economic Zone (EEZ) Boundaries
      {
        id: "eez-lines",
        type: "line",
        source: "eez-source",
        layout: {
          "line-join": "round",
          "line-cap": "round",
          visibility: "visible",
        },
        paint: {
          "line-color": "#3d4f9f",
          "line-width": 1.8,
          "line-opacity": 0.75,
          "line-dasharray": [6, 4],
        },
      },
      // 5. Shipping Lanes (TSS) Fill
      {
        id: "shipping-lanes-fill",
        type: "fill",
        source: "shipping-lanes-source",
        filter: ["==", "$type", "Polygon"],
        layout: {
          visibility: "visible",
        },
        paint: {
          "fill-color": "#fa6e39",
          "fill-opacity": 0.12,
        },
      },
      // 6. Shipping Lanes (TSS) Border & Transit Routes
      {
        id: "shipping-lanes-line",
        type: "line",
        source: "shipping-lanes-source",
        layout: {
          "line-join": "round",
          "line-cap": "round",
          visibility: "visible",
        },
        paint: {
          "line-color": "#fa6e39",
          "line-width": 1.5,
          "line-opacity": 0.65,
          "line-dasharray": [3, 2],
        },
      },
      // 7. Marine Protected Areas (MPA) Fill
      {
        id: "mpa-fill",
        type: "fill",
        source: "mpa-source",
        layout: {
          visibility: "visible",
        },
        paint: {
          "fill-color": "#00684a",
          "fill-opacity": 0.22,
        },
      },
      // 8. Marine Protected Areas (MPA) Border
      {
        id: "mpa-border",
        type: "line",
        source: "mpa-source",
        layout: {
          "line-join": "round",
          "line-cap": "round",
          visibility: "visible",
        },
        paint: {
          "line-color": "#00ed64",
          "line-width": 1.8,
          "line-opacity": 0.85,
        },
      },
    ],
  };
}
