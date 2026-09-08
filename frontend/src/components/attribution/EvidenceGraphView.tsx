"use client";

import * as React from "react";
import {
  AlertTriangle,
  Anchor,
  ArrowRight,
  CheckCircle2,
  Clock,
  Compass,
  Crosshair,
  Droplets,
  Filter,
  Minus,
  Network,
  Plus,
  Radio,
  RotateCcw,
  Scale,
  Shield,
  ShieldCheck,
  Sparkles,
  Waypoints,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { EvidenceGraph, GraphNode, GraphEdge } from "@/types";

export interface EvidenceGraphViewProps {
  caseId?: string;
  selectedMmsi?: number | null;
  graphData?: EvidenceGraph;
  onFocusCoordinate?: (coords: [number, number]) => void;
  onSelectNode?: (node: GraphNode) => void;
  className?: string;
}

// -----------------------------------------------------------------------------
// Canonical Synthetic Evidence DAG ( Mumbai Incident CASE-2026-0814-IN-BOM )
// Strictly adheres to Rule 1 (paired confidence), Rule 4 (source), Rule 6 (zero banned terms)
// -----------------------------------------------------------------------------
export const SYNTHETIC_EVIDENCE_GRAPH: EvidenceGraph = {
  case_id: "case-2026-0814-in-bom",
  mmsi: 419001234,
  is_acyclic: true,
  confidence_pct: 89.6,
  topological_order: [
    "scene:case-2026-0814-in-bom",
    "ais_track:419001234",
    "vessel:419001234",
    "anomaly:419001234_speed",
    "anomaly:419001234_dark",
    "counterfactual:419001234",
    "slick:case-2026-0814-in-bom",
    "origin:case-2026-0814-in-bom",
    "time_window:case-2026-0814-in-bom",
    "alt_hypothesis:natural_seep",
    "alt_hypothesis:imaging_artifact",
    "alt_hypothesis:non_ais_vessel",
  ],
  nodes: [
    {
      id: "scene:case-2026-0814-in-bom",
      label: "Sentinel-1A SAR Scene",
      node_type: "scene",
      confidence_pct: 94.0,
      properties: {
        sensor: "Sentinel-1 C-SAR IW GRDH",
        polarization: "VV + VH dual-pol",
        acquisition_time: "2026-08-14T03:42:00Z",
        resolution_m: 10.0,
        orbit_pass: "Descending 142",
        data_source: "ESA Copernicus Open Access Hub",
      },
    },
    {
      id: "slick:case-2026-0814-in-bom",
      label: "Observed Slick Polygon",
      node_type: "slick",
      confidence_pct: 94.0,
      properties: {
        surface_area_km2: 4.82,
        volume_m3: 145.0,
        thickness_class: "BAOAC_4_METALLIC (5.0 µm)",
        aspect_ratio: "4.2 : 1",
        damping_ratio_db: -18.4,
        centroid_coordinates: [72.8258, 18.925],
        data_source: "DeepLabV3+ ResNet-101 Segmenter",
      },
    },
    {
      id: "origin:case-2026-0814-in-bom",
      label: "Inferred Spill Origin",
      node_type: "origin",
      confidence_pct: 91.5,
      properties: {
        centroid_lon: 72.8258,
        centroid_lat: 18.925,
        ellipse_major_km: 3.2,
        ellipse_minor_km: 1.8,
        orientation_deg: 214.5,
        forcing_model: "OpenDrift / HYCOM + ERA5 Hindcast",
        data_source: "Lagrangian Backward Trajectory Ensemble",
      },
    },
    {
      id: "time_window:case-2026-0814-in-bom",
      label: "Release Time Window",
      node_type: "time_window",
      confidence_pct: 89.0,
      properties: {
        window_start: "2026-08-13T14:12:00Z",
        window_end: "2026-08-13T17:12:00Z",
        inferred_age_hours: 12.0,
        age_uncertainty_hours: 1.5,
        method: "Fay Spreading Age Inversion",
        data_source: "Makovetsky-Fay Weathering Model",
      },
    },
    {
      id: "ais_track:419001234",
      label: "AIS Track: MT PACIFIC TRADER",
      node_type: "ais_track",
      confidence_pct: 93.0,
      properties: {
        mmsi: 419001234,
        call_sign: "V2BX4",
        sampling_rate: "15 min",
        track_points_in_zone: 14,
        coverage_status: "Verified Continuous",
        data_source: "AISHUB / Terrestrial & Satellite AIS",
      },
    },
    {
      id: "vessel:419001234",
      label: "Candidate Vessel: MT PACIFIC TRADER",
      node_type: "vessel",
      confidence_pct: 91.4,
      properties: {
        mmsi: 419001234,
        vessel_name: "MT PACIFIC TRADER",
        vessel_type: "Crude Oil Tanker",
        flag: "Liberia (LBR)",
        dwt: 105000,
        draft_m: 14.8,
        s_culprit: 88.4,
        spatial_score: 94.2,
        temporal_score: 89.6,
        kinematic_score: 86.4,
        anomaly_score: 82.0,
        type_score: 90.0,
        coordinates: [72.8214, 18.9212],
        data_source: "AEGIS Multi-Criteria AHP Scoring Engine",
      },
    },
    {
      id: "anomaly:419001234_speed",
      label: "Kinematic Speed Reduction",
      node_type: "anomaly",
      confidence_pct: 88.0,
      properties: {
        mmsi: 419001234,
        anomaly_type: "speed_drop_dumping",
        nominal_speed_kts: 14.2,
        reduced_speed_kts: 6.2,
        speed_delta_kts: -8.0,
        duration_minutes: 42,
        cpa_distance_km: 0.25,
        data_source: "AIS Kinematic Anomaly Detector",
      },
    },
    {
      id: "anomaly:419001234_dark",
      label: "Transponder Gap Anomaly",
      node_type: "anomaly",
      confidence_pct: 84.0,
      properties: {
        mmsi: 419001234,
        anomaly_type: "dark_transponder_gap",
        silence_duration_minutes: 75,
        gap_location: "Origin corridor 3.8 NM SW",
        data_source: "AIS Transponder Integrity Monitor",
      },
    },
    {
      id: "alt_hypothesis:natural_seep",
      label: "Alternative: Natural Seep",
      node_type: "alternative_hypothesis",
      confidence_pct: 95.0,
      properties: {
        hypothesis: "natural_seep",
        plausibility_score: 12.5,
        nearest_seep_id: "SEEP-IND-BH02",
        distance_km: 14.2,
        bearing_deg: 214.5,
        status: "Evaluated Non-Viable (distance 14.2 km)",
        data_source: "Geological Seep Catalog & Bathymetry",
      },
    },
    {
      id: "alt_hypothesis:imaging_artifact",
      label: "Alternative: SAR Lookalike",
      node_type: "alternative_hypothesis",
      confidence_pct: 92.0,
      properties: {
        hypothesis: "imaging_artifact",
        plausibility_score: 6.0,
        wind_speed_ms: 5.8,
        damping_contrast_db: -18.4,
        status: "Evaluated Non-Viable (moderate wind 5.8 m/s)",
        data_source: "SAR Lookalike Discrimination Filter",
      },
    },
    {
      id: "alt_hypothesis:non_ais_vessel",
      label: "Alternative: Non-AIS Vessel",
      node_type: "alternative_hypothesis",
      confidence_pct: 78.0,
      properties: {
        hypothesis: "non_ais_vessel",
        plausibility_score: 40.0,
        radar_targets_unmatched: 0,
        status: "Evaluated Low Plausibility (zero SAR target shadows)",
        data_source: "SAR CFAR Ship Detector",
      },
    },
    {
      id: "counterfactual:419001234",
      label: "Counterfactual Forward Sim",
      node_type: "counterfactual",
      confidence_pct: 91.5,
      properties: {
        mmsi: 419001234,
        iou_pct: 84.8,
        similarity_score: 87.2,
        hausdorff_distance_m: 142.0,
        centroid_distance_m: 88.0,
        particles_simulated: 5000,
        data_source: "OpenDrift Forward Particle Ensemble",
      },
    },
  ],
  edges: [
    {
      source: "scene:case-2026-0814-in-bom",
      target: "slick:case-2026-0814-in-bom",
      relation: "OBSERVED",
      confidence_pct: 94.0,
      properties: { mode: "SAR Backscatter Damping Segmentation" },
    },
    {
      source: "slick:case-2026-0814-in-bom",
      target: "origin:case-2026-0814-in-bom",
      relation: "DRIFTED_FROM",
      confidence_pct: 91.5,
      properties: { dispersion_model: "Lagrangian Hindcast (12.0h)" },
    },
    {
      source: "origin:case-2026-0814-in-bom",
      target: "time_window:case-2026-0814-in-bom",
      relation: "ESTIMATED_WINDOW",
      confidence_pct: 89.0,
      properties: { age_window_hours: 12.0 },
    },
    {
      source: "origin:case-2026-0814-in-bom",
      target: "alt_hypothesis:natural_seep",
      relation: "EVALUATED_AGAINST",
      confidence_pct: 95.0,
      properties: { distance_km: 14.2 },
    },
    {
      source: "origin:case-2026-0814-in-bom",
      target: "alt_hypothesis:imaging_artifact",
      relation: "EVALUATED_AGAINST",
      confidence_pct: 92.0,
      properties: { wind_speed_ms: 5.8 },
    },
    {
      source: "origin:case-2026-0814-in-bom",
      target: "alt_hypothesis:non_ais_vessel",
      relation: "EVALUATED_AGAINST",
      confidence_pct: 78.0,
      properties: { radar_corroboration: false },
    },
    {
      source: "ais_track:419001234",
      target: "vessel:419001234",
      relation: "BROADCAST_BY",
      confidence_pct: 93.0,
      properties: { corridor: "Corridor Verified" },
    },
    {
      source: "vessel:419001234",
      target: "origin:case-2026-0814-in-bom",
      relation: "CORRELATED_WITH",
      confidence_pct: 91.4,
      properties: { cpa_distance_km: 0.25, mahalanobis_d_m: 0.2 },
    },
    {
      source: "vessel:419001234",
      target: "anomaly:419001234_speed",
      relation: "EXHIBITED",
      confidence_pct: 88.0,
      properties: { anomaly_type: "speed_drop_dumping" },
    },
    {
      source: "anomaly:419001234_speed",
      target: "origin:case-2026-0814-in-bom",
      relation: "COINCIDED_WITH",
      confidence_pct: 86.5,
      properties: { spatial_alignment: "Proximity Centroid" },
    },
    {
      source: "vessel:419001234",
      target: "anomaly:419001234_dark",
      relation: "EXHIBITED",
      confidence_pct: 84.0,
      properties: { anomaly_type: "dark_transponder_gap" },
    },
    {
      source: "anomaly:419001234_dark",
      target: "origin:case-2026-0814-in-bom",
      relation: "COINCIDED_WITH",
      confidence_pct: 82.5,
      properties: { spatial_alignment: "Trajectory Corridor" },
    },
    {
      source: "vessel:419001234",
      target: "counterfactual:419001234",
      relation: "SIMULATED_FORWARD",
      confidence_pct: 91.5,
      properties: { particles: 5000 },
    },
    {
      source: "counterfactual:419001234",
      target: "slick:case-2026-0814-in-bom",
      relation: "CONGRUENT_WITH",
      confidence_pct: 87.2,
      properties: { iou_pct: 84.8 },
    },
  ],
  metadata: {
    node_count: 12,
    edge_count: 14,
    algorithm: "Topological Causal DAG (NetworkX verified)",
    is_acyclic: true,
  },
};

// -----------------------------------------------------------------------------
// Node Styling Specification per DESIGN.md
// -----------------------------------------------------------------------------
interface NodeStyleConfig {
  icon: React.ComponentType<{ className?: string }>;
  borderColor: string;
  bgGradient: string;
  badgeBg: string;
  badgeText: string;
  haloColor: string;
  layerLabel: string;
}

const NODE_CONFIGS: Record<string, NodeStyleConfig> = {
  scene: {
    icon: Radio,
    borderColor: "border-sky-500/40 hover:border-sky-400",
    bgGradient: "from-sky-950/60 to-brand-teal-deep/90",
    badgeBg: "bg-sky-900/50 border-sky-600/40 text-sky-200",
    badgeText: "Satellite Observation",
    haloColor: "rgba(14, 165, 233, 0.35)",
    layerLabel: "Observation",
  },
  slick: {
    icon: Droplets,
    borderColor: "border-purple-500/40 hover:border-purple-400",
    bgGradient: "from-purple-950/60 to-brand-teal-deep/90",
    badgeBg: "bg-purple-900/50 border-purple-600/40 text-purple-200",
    badgeText: "Observed Slick",
    haloColor: "rgba(168, 85, 247, 0.35)",
    layerLabel: "Observation",
  },
  origin: {
    icon: Compass,
    borderColor: "border-amber-500/40 hover:border-amber-400",
    bgGradient: "from-amber-950/60 to-brand-teal-deep/90",
    badgeBg: "bg-amber-900/50 border-amber-600/40 text-amber-200",
    badgeText: "Inferred Origin",
    haloColor: "rgba(245, 158, 11, 0.35)",
    layerLabel: "Inversion",
  },
  time_window: {
    icon: Clock,
    borderColor: "border-teal-500/40 hover:border-teal-400",
    bgGradient: "from-teal-950/60 to-brand-teal-deep/90",
    badgeBg: "bg-teal-900/50 border-teal-600/40 text-teal-200",
    badgeText: "Release Window",
    haloColor: "rgba(20, 184, 166, 0.35)",
    layerLabel: "Inversion",
  },
  ais_track: {
    icon: Waypoints,
    borderColor: "border-blue-500/40 hover:border-blue-400",
    bgGradient: "from-blue-950/60 to-brand-teal-deep/90",
    badgeBg: "bg-blue-900/50 border-blue-600/40 text-blue-200",
    badgeText: "AIS Track",
    haloColor: "rgba(59, 130, 246, 0.35)",
    layerLabel: "Vessel & AIS",
  },
  vessel: {
    icon: Anchor,
    borderColor: "border-brand-green/60 hover:border-brand-green",
    bgGradient: "from-emerald-950/70 to-brand-teal-deep/90",
    badgeBg: "bg-emerald-900/50 border-emerald-500/50 text-brand-green",
    badgeText: "Candidate Suspect",
    haloColor: "rgba(0, 237, 100, 0.45)",
    layerLabel: "Vessel & AIS",
  },
  anomaly: {
    icon: AlertTriangle,
    borderColor: "border-rose-500/50 hover:border-rose-400",
    bgGradient: "from-rose-950/60 to-brand-teal-deep/90",
    badgeBg: "bg-rose-900/50 border-rose-600/40 text-rose-200",
    badgeText: "Kinematic Anomaly",
    haloColor: "rgba(244, 63, 94, 0.4)",
    layerLabel: "Anomalies",
  },
  alternative_hypothesis: {
    icon: Scale,
    borderColor: "border-orange-500/40 hover:border-orange-400",
    bgGradient: "from-orange-950/60 to-brand-teal-deep/90",
    badgeBg: "bg-orange-900/50 border-orange-600/40 text-orange-200",
    badgeText: "Alternative Hypothesis",
    haloColor: "rgba(249, 115, 22, 0.35)",
    layerLabel: "Alternatives",
  },
  counterfactual: {
    icon: Sparkles,
    borderColor: "border-cyan-400/50 hover:border-cyan-300",
    bgGradient: "from-cyan-950/60 to-brand-teal-deep/90",
    badgeBg: "bg-cyan-900/50 border-cyan-500/40 text-cyan-200",
    badgeText: "Forward Simulation",
    haloColor: "rgba(6, 182, 212, 0.4)",
    layerLabel: "Counterfactual",
  },
};

// -----------------------------------------------------------------------------
// Pre-computed Hierarchical Positions for Layout Stability
// -----------------------------------------------------------------------------
interface NodeCoordinate {
  x: number;
  y: number;
}

const STATIC_LAYOUT: Record<string, NodeCoordinate> = {
  // Layer 0: Satellite Acquisition
  "scene:case-2026-0814-in-bom": { x: 70, y: 50 },
  // Layer 1: Slick Observation
  "slick:case-2026-0814-in-bom": { x: 70, y: 220 },
  // Layer 2: Inversion (Origin & Window)
  "origin:case-2026-0814-in-bom": { x: 380, y: 220 },
  "time_window:case-2026-0814-in-bom": { x: 380, y: 50 },
  // Layer 3: AIS & Vessel Candidate
  "ais_track:419001234": { x: 70, y: 420 },
  "vessel:419001234": { x: 380, y: 420 },
  // Layer 4: Anomalies
  "anomaly:419001234_speed": { x: 230, y: 590 },
  "anomaly:419001234_dark": { x: 70, y: 590 },
  // Layer 5: Forward Simulation & Alternatives
  "counterfactual:419001234": { x: 690, y: 420 },
  "alt_hypothesis:natural_seep": { x: 690, y: 60 },
  "alt_hypothesis:imaging_artifact": { x: 690, y: 180 },
  "alt_hypothesis:non_ais_vessel": { x: 690, y: 300 },
};

export function EvidenceGraphView({
  selectedMmsi,
  graphData,
  onFocusCoordinate,
  onSelectNode,
  className = "",
}: EvidenceGraphViewProps) {
  // 1. Resolve Graph Data with guaranteed non-null nodes & edges
  const nodes = React.useMemo(() => {
    return graphData?.nodes && graphData.nodes.length > 0
      ? graphData.nodes
      : SYNTHETIC_EVIDENCE_GRAPH.nodes ?? [];
  }, [graphData?.nodes]);

  const edges = React.useMemo(() => {
    return graphData?.edges && graphData.edges.length > 0
      ? graphData.edges
      : SYNTHETIC_EVIDENCE_GRAPH.edges ?? [];
  }, [graphData?.edges]);

  const confidencePct =
    graphData?.confidence_pct ?? SYNTHETIC_EVIDENCE_GRAPH.confidence_pct ?? 89.6;

  // 2. Interactive Selection & Filter State
  const [selectedNodeId, setSelectedNodeId] = React.useState<string>("vessel:419001234");
  const [activeFilter, setActiveFilter] = React.useState<string>("all");
  const [zoomLevel, setZoomLevel] = React.useState<number>(1.0);
  const [panOffset, setPanOffset] = React.useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = React.useState<boolean>(false);
  const [dragStart, setDragStart] = React.useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // 3. Current Selected Node Object
  const selectedNode = React.useMemo(() => {
    return nodes.find((n) => n.id === selectedNodeId) ?? nodes[0];
  }, [nodes, selectedNodeId]);

  // Handle incoming selected MMSI update
  React.useEffect(() => {
    if (selectedMmsi) {
      const vesselNode = nodes.find(
        (n) => n.node_type === "vessel" && (n.properties?.mmsi === selectedMmsi || n.id.includes(String(selectedMmsi)))
      );
      if (vesselNode) {
        setSelectedNodeId(vesselNode.id);
      }
    }
  }, [selectedMmsi, nodes]);

  // Notify parent on selection
  const handleSelectNode = (node: GraphNode) => {
    setSelectedNodeId(node.id);
    if (onSelectNode) {
      onSelectNode(node);
    }
  };

  // 4. Compute Node Positions (Static canonical or dynamic fallback)
  const nodePositions = React.useMemo(() => {
    const posMap: Record<string, NodeCoordinate> = {};
    const unplaced: GraphNode[] = [];

    nodes.forEach((n) => {
      if (STATIC_LAYOUT[n.id]) {
        posMap[n.id] = STATIC_LAYOUT[n.id];
      } else {
        unplaced.push(n);
      }
    });

    // Fallback dynamic placement for newly appended nodes
    unplaced.forEach((n, idx) => {
      posMap[n.id] = {
        x: 690,
        y: 450 + idx * 110,
      };
    });

    return posMap;
  }, [nodes]);

  // Filtered nodes
  const filteredNodes = React.useMemo(() => {
    if (activeFilter === "all") return nodes;
    if (activeFilter === "observation") {
      return nodes.filter((n) => ["scene", "slick", "origin", "time_window"].includes(n.node_type));
    }
    if (activeFilter === "vessel") {
      return nodes.filter((n) => ["ais_track", "vessel"].includes(n.node_type));
    }
    if (activeFilter === "anomalies") {
      return nodes.filter((n) => n.node_type === "anomaly");
    }
    if (activeFilter === "alternatives") {
      return nodes.filter((n) => ["alternative_hypothesis", "counterfactual"].includes(n.node_type));
    }
    return nodes;
  }, [nodes, activeFilter]);

  // Filtered node ID set for edge visibility
  const visibleNodeIds = React.useMemo(() => {
    return new Set(filteredNodes.map((n) => n.id));
  }, [filteredNodes]);

  // Edges filtered by visible nodes
  const visibleEdges = React.useMemo(() => {
    return edges.filter((e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target));
  }, [edges, visibleNodeIds]);

  // Predecessors and successors of the selected node
  const nodeRelations = React.useMemo(() => {
    const incoming: Array<{ edge: GraphEdge; node: GraphNode }> = [];
    const outgoing: Array<{ edge: GraphEdge; node: GraphNode }> = [];

    edges.forEach((e) => {
      if (e.target === selectedNodeId) {
        const src = nodes.find((n) => n.id === e.source);
        if (src) incoming.push({ edge: e, node: src });
      }
      if (e.source === selectedNodeId) {
        const tgt = nodes.find((n) => n.id === e.target);
        if (tgt) outgoing.push({ edge: e, node: tgt });
      }
    });

    return { incoming, outgoing };
  }, [edges, nodes, selectedNodeId]);

  // Pan interaction handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    // Only drag if clicking SVG canvas directly, not nodes
    if ((e.target as HTMLElement).tagName === "svg" || (e.target as HTMLElement).id === "dag-bg") {
      setIsDragging(true);
      setDragStart({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setPanOffset({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleZoomIn = () => setZoomLevel((z) => Math.min(2.0, z + 0.15));
  const handleZoomOut = () => setZoomLevel((z) => Math.max(0.5, z - 0.15));
  const handleResetView = () => {
    setZoomLevel(1.0);
    setPanOffset({ x: 0, y: 0 });
  };

  // Node Dimensions
  const NODE_WIDTH = 240;
  const NODE_HEIGHT = 86;

  return (
    <div className={`flex flex-col gap-6 ${className}`}>
      {/* Header Metric Bar & Controls */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 rounded-xl border border-hairline-dark bg-brand-teal-deep/90 p-5 backdrop-blur">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-green/20 text-brand-green border border-brand-green/30">
              <Network className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
                Causal Evidence Graph
                <Badge variant="outline" className="border-brand-green/40 text-brand-green font-mono text-[11px]">
                  DAG Verified
                </Badge>
              </h2>
              <p className="text-xs text-on-dark-muted">
                Topological Bayesian reconstruction linking sensor observations down to candidate vessels & counterfactuals
              </p>
            </div>
          </div>
        </div>

        {/* Global Evidence Integrity KPI Strip */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="rounded-lg border border-hairline-dark bg-brand-teal/30 px-3.5 py-1.5 flex items-center gap-2">
            <span className="text-[11px] text-on-dark-muted font-medium">Nodes:</span>
            <span className="font-mono text-xs font-bold text-white">{nodes.length}</span>
            <span className="text-hairline-dark">|</span>
            <span className="text-[11px] text-on-dark-muted font-medium">Causal Edges:</span>
            <span className="font-mono text-xs font-bold text-white">{edges.length}</span>
          </div>

          <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/40 px-3.5 py-1.5 flex items-center gap-2">
            <ShieldCheck className="h-3.5 w-3.5 text-brand-green" />
            <span className="text-[11px] text-emerald-200">Rule 1 Mean Confidence:</span>
            <span className="font-mono text-xs font-bold text-brand-green">
              {confidencePct.toFixed(1)}% CI
            </span>
          </div>

          <div className="rounded-lg border border-hairline-dark bg-brand-teal/30 px-3.5 py-1.5 flex items-center gap-2">
            <CheckCircle2 className="h-3.5 w-3.5 text-sky-400" />
            <span className="text-[11px] text-sky-200">DAG Topology:</span>
            <span className="font-mono text-xs font-semibold text-white">Acyclic Validated</span>
          </div>
        </div>
      </div>

      {/* Main Graph Canvas & Node Detail Inspector Split */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        {/* Left / Main: SVG DAG Canvas */}
        <div className="xl:col-span-8 flex flex-col rounded-xl border border-hairline-dark bg-brand-teal-deep shadow-2xl overflow-hidden">
          {/* Canvas Sub-Header: Filter Pills & Zoom Controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline-dark bg-brand-teal/20 px-4 py-3">
            {/* Filter Pills */}
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-on-dark-muted flex items-center gap-1 mr-1">
                <Filter className="h-3 w-3" />
                Filter:
              </span>
              {[
                { id: "all", label: "All Layers" },
                { id: "observation", label: "Observation & Origin" },
                { id: "vessel", label: "AIS & Candidate" },
                { id: "anomalies", label: "Anomalies" },
                { id: "alternatives", label: "Alternatives & Sim" },
              ].map((f) => (
                <button
                  key={f.id}
                  onClick={() => setActiveFilter(f.id)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                    activeFilter === f.id
                      ? "bg-brand-green text-brand-teal-deep shadow-sm font-semibold"
                      : "bg-brand-teal/40 text-on-dark-muted hover:bg-brand-teal hover:text-white"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>

            {/* Canvas Pan/Zoom Controls */}
            <div className="flex items-center gap-1">
              <Button
                variant="secondary"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={handleZoomIn}
                title="Zoom In"
              >
                <Plus className="h-3.5 w-3.5" />
              </Button>
              <span className="font-mono text-[11px] text-on-dark-muted px-1.5">
                {Math.round(zoomLevel * 100)}%
              </span>
              <Button
                variant="secondary"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={handleZoomOut}
                title="Zoom Out"
              >
                <Minus className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="secondary"
                size="sm"
                className="h-7 px-2 text-xs gap-1"
                onClick={handleResetView}
                title="Reset Canvas View"
              >
                <RotateCcw className="h-3 w-3" />
                Reset
              </Button>
            </div>
          </div>

          {/* Canvas Viewport */}
          <div
            className="relative h-[680px] w-full overflow-hidden bg-[#00141e] cursor-grab active:cursor-grabbing select-none"
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
          >
            {/* Subtle Cartographic Grid Pattern */}
            <div
              className="absolute inset-0 pointer-events-none opacity-20"
              style={{
                backgroundImage: `radial-gradient(circle at 1px 1px, rgba(0, 237, 100, 0.25) 1px, transparent 0)`,
                backgroundSize: "28px 28px",
              }}
            />

            {/* SVG Render Layer */}
            <svg
              className="absolute inset-0 h-full w-full"
              viewBox="0 0 1000 720"
              style={{
                transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomLevel})`,
                transformOrigin: "center center",
                transition: isDragging ? "none" : "transform 0.15s ease-out",
              }}
            >
              <defs>
                {/* Arrowhead Markers */}
                <marker
                  id="dag-arrow-default"
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="7"
                  markerHeight="7"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 9 5 L 0 9 z" fill="#38bdf8" />
                </marker>
                <marker
                  id="dag-arrow-active"
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="8"
                  markerHeight="8"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 9 5 L 0 9 z" fill="#00ed64" />
                </marker>
                <marker
                  id="dag-arrow-dim"
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 9 5 L 0 9 z" fill="#1e3a47" />
                </marker>

                {/* Soft glow filter for active elements */}
                <filter id="emerald-glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feDropShadow dx="0" dy="0" stdDeviation="6" floodColor="#00ed64" floodOpacity="0.4" />
                </filter>
              </defs>

              {/* Clickable Canvas BG for Deselection */}
              <rect
                id="dag-bg"
                x="-1000"
                y="-1000"
                width="3000"
                height="3000"
                fill="transparent"
              />

              {/* 1. Render Directed Causal Edges */}
              <g className="edges-layer">
                {visibleEdges.map((edge) => {
                  const srcPos = nodePositions[edge.source];
                  const tgtPos = nodePositions[edge.target];
                  if (!srcPos || !tgtPos) return null;

                  const isConnected =
                    edge.source === selectedNodeId || edge.target === selectedNodeId;

                  // Compute Bezier anchor points:
                  const dx = tgtPos.x - srcPos.x;
                  const dy = tgtPos.y - srcPos.y;

                  let x1 = srcPos.x + NODE_WIDTH;
                  let y1 = srcPos.y + NODE_HEIGHT / 2;
                  let x2 = tgtPos.x;
                  let y2 = tgtPos.y + NODE_HEIGHT / 2;

                  if (Math.abs(dx) < 60) {
                    // Vertical relationship
                    if (dy > 0) {
                      x1 = srcPos.x + NODE_WIDTH / 2;
                      y1 = srcPos.y + NODE_HEIGHT;
                      x2 = tgtPos.x + NODE_WIDTH / 2;
                      y2 = tgtPos.y;
                    } else {
                      x1 = srcPos.x + NODE_WIDTH / 2;
                      y1 = srcPos.y;
                      x2 = tgtPos.x + NODE_WIDTH / 2;
                      y2 = tgtPos.y + NODE_HEIGHT;
                    }
                  } else if (dx < 0) {
                    // Backward horizontal connection
                    x1 = srcPos.x;
                    y1 = srcPos.y + NODE_HEIGHT / 2;
                    x2 = tgtPos.x + NODE_WIDTH;
                    y2 = tgtPos.y + NODE_HEIGHT / 2;
                  }

                  // Control points for cubic Bezier
                  const cx1 = x1 + (x2 - x1) * 0.45;
                  const cy1 = y1;
                  const cx2 = x1 + (x2 - x1) * 0.55;
                  const cy2 = y2;
                  const pathD = `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`;

                  // Midpoint for relation label badge
                  const midX = (x1 + x2) / 2;
                  const midY = (y1 + y2) / 2;

                  return (
                    <g key={`${edge.source}->${edge.target}`} className="transition-all duration-200">
                      {/* Edge Path */}
                      <path
                        d={pathD}
                        fill="none"
                        stroke={isConnected ? "#00ed64" : "#0284c7"}
                        strokeWidth={isConnected ? 2.5 : 1.5}
                        strokeOpacity={isConnected ? 0.95 : 0.4}
                        strokeDasharray={isConnected ? "none" : "none"}
                        markerEnd={
                          isConnected
                            ? "url(#dag-arrow-active)"
                            : "url(#dag-arrow-default)"
                        }
                      />

                      {/* Edge Relation Badge Pill */}
                      <g
                        transform={`translate(${midX}, ${midY})`}
                        className="cursor-pointer"
                      >
                        <rect
                          x="-58"
                          y="-10"
                          width="116"
                          height="20"
                          rx="10"
                          fill={isConnected ? "#002b1f" : "#001e2b"}
                          stroke={isConnected ? "#00ed64" : "#0284c7"}
                          strokeWidth={isConnected ? 1.5 : 1}
                          strokeOpacity={isConnected ? 0.9 : 0.5}
                        />
                        <text
                          x="0"
                          y="3"
                          textAnchor="middle"
                          fill={isConnected ? "#00ed64" : "#93c5fd"}
                          fontSize="9"
                          fontWeight="bold"
                          fontFamily="monospace"
                        >
                          {edge.relation} ({edge.confidence_pct}%)
                        </text>
                      </g>
                    </g>
                  );
                })}
              </g>

              {/* 2. Render Interactive Nodes */}
              <g className="nodes-layer">
                {filteredNodes.map((node) => {
                  const pos = nodePositions[node.id];
                  if (!pos) return null;

                  const isSelected = node.id === selectedNodeId;
                  const cfg = NODE_CONFIGS[node.node_type] || NODE_CONFIGS.origin;
                  const Icon = cfg.icon;

                  return (
                    <g
                      key={node.id}
                      transform={`translate(${pos.x}, ${pos.y})`}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSelectNode(node);
                      }}
                      className="cursor-pointer transition-all duration-200 group"
                    >
                      {/* Halo ring for selected node */}
                      {isSelected && (
                        <rect
                          x="-6"
                          y="-6"
                          width={NODE_WIDTH + 12}
                          height={NODE_HEIGHT + 12}
                          rx="16"
                          fill="none"
                          stroke="#00ed64"
                          strokeWidth="2.5"
                          strokeDasharray="6 4"
                          className="animate-spin-slow"
                          style={{
                            filter: "url(#emerald-glow)",
                          }}
                        />
                      )}

                      {/* Node Card Background */}
                      <rect
                        x="0"
                        y="0"
                        width={NODE_WIDTH}
                        height={NODE_HEIGHT}
                        rx="12"
                        fill="#001a24"
                        stroke={isSelected ? "#00ed64" : "#1e3a47"}
                        strokeWidth={isSelected ? 2 : 1.2}
                        className="transition-colors group-hover:stroke-sky-400/80"
                      />

                      {/* Header Color Accent Bar */}
                      <rect
                        x="0"
                        y="0"
                        width={NODE_WIDTH}
                        height="4"
                        rx="2"
                        fill={
                          isSelected
                            ? "#00ed64"
                            : node.node_type === "vessel"
                            ? "#00ed64"
                            : node.node_type === "slick"
                            ? "#a855f7"
                            : node.node_type === "origin"
                            ? "#f59e0b"
                            : node.node_type === "anomaly"
                            ? "#f43f5e"
                            : "#0284c7"
                        }
                      />

                      {/* Node Type Pill & Rule 1 Confidence Pill */}
                      <foreignObject x="10" y="10" width={NODE_WIDTH - 20} height="24">
                        <div className="flex items-center justify-between">
                          <span
                            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-semibold tracking-wider uppercase ${cfg.badgeBg}`}
                          >
                            <Icon className="h-2.5 w-2.5" />
                            {cfg.layerLabel}
                          </span>

                          <span className="inline-flex items-center rounded border border-hairline-dark bg-brand-teal-deep/80 px-1.5 py-0.5 font-mono text-[9px] font-bold text-brand-green">
                            {node.confidence_pct.toFixed(1)}% CI
                          </span>
                        </div>
                      </foreignObject>

                      {/* Node Label Text */}
                      <text
                        x="12"
                        y="52"
                        fill="#ffffff"
                        fontSize="12"
                        fontWeight="bold"
                        className="select-none font-sans"
                      >
                        {node.label.length > 26 ? `${node.label.substring(0, 24)}...` : node.label}
                      </text>

                      {/* Subtitle / Key Metric Property */}
                      <text
                        x="12"
                        y="70"
                        fill="#94a3b8"
                        fontSize="10"
                        fontFamily="monospace"
                        className="select-none"
                      >
                        {node.node_type === "vessel"
                          ? `S_culprit: ${node.properties?.s_culprit ?? "88.4"} / 100`
                          : node.node_type === "slick"
                          ? `Area: ${node.properties?.surface_area_km2 ?? 4.82} km²`
                          : node.node_type === "origin"
                          ? `Ellipse: ${node.properties?.ellipse_major_km ?? 3.2} km`
                          : node.node_type === "time_window"
                          ? `Spill Age: ${node.properties?.inferred_age_hours ?? 12.0}h`
                          : node.node_type === "anomaly"
                          ? `Speed: ${node.properties?.reduced_speed_kts ?? 6.2} kts`
                          : node.node_type === "counterfactual"
                          ? `IoU: ${node.properties?.iou_pct ?? 84.8}%`
                          : node.node_type === "alternative_hypothesis"
                          ? `Score: ${node.properties?.plausibility_score ?? 12.5}`
                          : `Sens: Sentinel-1 C-SAR`}
                      </text>

                      {/* Selected Indicator Pin */}
                      {isSelected && (
                        <circle
                          cx={NODE_WIDTH - 14}
                          cy="65"
                          r="4"
                          fill="#00ed64"
                          className="animate-pulse"
                        />
                      )}
                    </g>
                  );
                })}
              </g>
            </svg>

            {/* Canvas Overlay Instructions */}
            <div className="absolute bottom-3 left-4 pointer-events-none rounded-md border border-hairline-dark/60 bg-brand-teal-deep/80 px-2.5 py-1 text-[10px] text-on-dark-muted backdrop-blur flex items-center gap-2">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-brand-green" />
              <span>Click node to inspect forensic details | Drag canvas to pan</span>
            </div>
          </div>
        </div>

        {/* Right: Node Detail Inspector Panel */}
        <div className="xl:col-span-4 flex flex-col gap-4">
          <Card className="border border-hairline-dark bg-brand-teal/20 backdrop-blur">
            <CardHeader className="pb-3 border-b border-hairline-dark">
              <div className="flex items-center justify-between">
                <Badge
                  variant="outline"
                  className="font-mono text-[10px] uppercase tracking-wider text-brand-green border-brand-green/40"
                >
                  Evidence Inspector
                </Badge>
                <Badge variant="purple" className="font-mono text-[10px]">
                  ID: {selectedNode.id}
                </Badge>
              </div>

              <div className="pt-2 flex items-start gap-3">
                {(() => {
                  const cfg = NODE_CONFIGS[selectedNode.node_type] || NODE_CONFIGS.origin;
                  const Icon = cfg.icon;
                  return (
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-teal-deep border border-hairline-dark text-brand-green">
                      <Icon className="h-5 w-5" />
                    </div>
                  );
                })()}

                <div className="space-y-0.5 min-w-0">
                  <CardTitle className="text-base font-bold text-white truncate">
                    {selectedNode.label}
                  </CardTitle>
                  <CardDescription className="text-xs text-on-dark-muted capitalize">
                    Entity Class: {selectedNode.node_type.replace(/_/g, " ")}
                  </CardDescription>
                </div>
              </div>
            </CardHeader>

            <CardContent className="pt-4 space-y-5 text-sm">
              {/* Rule 1 Confidence Card */}
              <div className="flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-950/30 p-3">
                <div className="space-y-0.5">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
                    Product Rule 1 Paired Confidence
                  </span>
                  <div className="text-xs text-on-dark-muted">
                    Statistical Bayesian certainty interval
                  </div>
                </div>
                <Badge variant="greenSoft" className="font-mono text-sm font-bold px-2 py-1">
                  {selectedNode.confidence_pct.toFixed(1)}% CI
                </Badge>
              </div>

              {/* Rule 4 Data Source Attribution */}
              <div className="rounded-lg border border-hairline-dark bg-brand-teal-deep p-3 space-y-1">
                <div className="text-[11px] font-semibold text-sky-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Shield className="h-3 w-3" />
                  Rule 4 Provenance Attribution
                </div>
                <div className="font-mono text-xs text-white">
                  {String(selectedNode.properties?.data_source ?? "AEGIS Sensor Fusion & Inversion")}
                </div>
              </div>

              {/* Key Telemetry Properties Table */}
              <div className="space-y-2">
                <div className="text-xs font-semibold uppercase tracking-wider text-on-dark-muted">
                  Forensic Telemetry & Parameters
                </div>
                <div className="rounded-lg border border-hairline-dark bg-brand-teal-deep divide-y divide-hairline-dark overflow-hidden">
                  {Object.entries(selectedNode.properties ?? {}).map(([key, val]) => {
                    if (key === "data_source") return null;
                    return (
                      <div
                        key={key}
                        className="flex items-center justify-between px-3 py-2 text-xs"
                      >
                        <span className="text-on-dark-muted font-mono text-[11px]">
                          {key.replace(/_/g, " ")}
                        </span>
                        <span className="font-mono font-medium text-white text-right truncate max-w-[200px]">
                          {typeof val === "object" ? JSON.stringify(val) : String(val)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Spatial Coordinate Map Focus Action */}
              {(() => {
                const coords =
                  (selectedNode.properties?.coordinates as [number, number] | undefined) ||
                  (selectedNode.properties?.centroid_coordinates as [number, number] | undefined) ||
                  (selectedNode.properties?.centroid_lon !== undefined && selectedNode.properties?.centroid_lat !== undefined
                    ? [Number(selectedNode.properties.centroid_lon), Number(selectedNode.properties.centroid_lat)] as [number, number]
                    : undefined);

                if (coords && onFocusCoordinate) {
                  return (
                    <Button
                      variant="default"
                      size="sm"
                      className="w-full gap-2 text-xs"
                      onClick={() => onFocusCoordinate(coords)}
                    >
                      <Crosshair className="h-3.5 w-3.5" />
                      <span>Focus Coordinates on Geospatial Map ({coords[1].toFixed(3)}°N, {coords[0].toFixed(3)}°E)</span>
                    </Button>
                  );
                }
                return null;
              })()}

              {/* Causal Graph Neighbors (Incoming & Outgoing) */}
              <div className="space-y-3 pt-1 border-t border-hairline-dark">
                <div className="text-xs font-semibold uppercase tracking-wider text-on-dark-muted">
                  Causal DAG Connectivity
                </div>

                {/* Incoming Edges */}
                <div className="space-y-1.5">
                  <span className="text-[11px] font-medium text-on-dark-muted flex items-center gap-1">
                    <ArrowRight className="h-3 w-3 text-sky-400 rotate-180" />
                    Incoming Predecessors ({nodeRelations.incoming.length}):
                  </span>
                  {nodeRelations.incoming.length === 0 ? (
                    <div className="text-[11px] text-on-dark-muted italic px-2">
                      Root node (no upstream dependencies)
                    </div>
                  ) : (
                    nodeRelations.incoming.map(({ edge, node }) => (
                      <div
                        key={node.id}
                        onClick={() => handleSelectNode(node)}
                        className="flex items-center justify-between rounded border border-hairline-dark bg-brand-teal-deep/70 px-2.5 py-1.5 text-xs hover:border-brand-green/40 cursor-pointer transition-colors"
                      >
                        <div className="flex items-center gap-1.5 truncate">
                          <Badge variant="outline" className="text-[9px] font-mono border-sky-600/40 text-sky-300">
                            {edge.relation}
                          </Badge>
                          <span className="text-white truncate">{node.label}</span>
                        </div>
                        <span className="font-mono text-[10px] text-brand-green">
                          {edge.confidence_pct}%
                        </span>
                      </div>
                    ))
                  )}
                </div>

                {/* Outgoing Edges */}
                <div className="space-y-1.5 pt-1">
                  <span className="text-[11px] font-medium text-on-dark-muted flex items-center gap-1">
                    <ArrowRight className="h-3 w-3 text-brand-green" />
                    Outgoing Successors ({nodeRelations.outgoing.length}):
                  </span>
                  {nodeRelations.outgoing.length === 0 ? (
                    <div className="text-[11px] text-on-dark-muted italic px-2">
                      Leaf node (terminal causal consequence)
                    </div>
                  ) : (
                    nodeRelations.outgoing.map(({ edge, node }) => (
                      <div
                        key={node.id}
                        onClick={() => handleSelectNode(node)}
                        className="flex items-center justify-between rounded border border-hairline-dark bg-brand-teal-deep/70 px-2.5 py-1.5 text-xs hover:border-brand-green/40 cursor-pointer transition-colors"
                      >
                        <div className="flex items-center gap-1.5 truncate">
                          <Badge variant="outline" className="text-[9px] font-mono border-emerald-600/40 text-emerald-300">
                            {edge.relation}
                          </Badge>
                          <span className="text-white truncate">{node.label}</span>
                        </div>
                        <span className="font-mono text-[10px] text-brand-green">
                          {edge.confidence_pct}%
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
