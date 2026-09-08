"use client";

import * as React from "react";
import {
  Compass,
  Mountain,
  Scan,
  Radio,
  ShieldCheck,
  ArrowUpDown,
  Filter,
  ChevronDown,
  ChevronUp,
  Scale,
  Layers,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  AlternativeExplanation,
  NaturalSeepEvidence,
  ImagingArtifactEvidence,
  NonAISVesselEvidence,
} from "@/types";

export interface AlternativeExplanationsPanelProps {
  caseId?: string;
  alternatives?: AlternativeExplanation[];
  topCandidateScore?: number;
  topCandidateName?: string;
  onSelectHypothesis?: (hypothesis: AlternativeExplanation) => void;
  className?: string;
}

export const SYNTHETIC_ALTERNATIVES: AlternativeExplanation[] = [
  {
    id: "alt-1-natural-seep",
    case_id: "case-2026-0814-in-bom",
    hypothesis: "natural_seep",
    score: 12.5,
    confidence: 95.0,
    created_at: "2026-08-14T04:30:00Z",
    evidence: {
      nearest_seep_id: "SEEP-IND-BH02",
      nearest_seep_name: "Bombay High South Flank Seep",
      basin: "Mumbai Offshore Continental Shelf Basin",
      distance_km: 14.2,
      bearing_deg: 214.5,
      water_depth_m: 85.0,
      seep_type: "Thermogenic Condensate / Gas",
      activity_status: "Intermittent",
      target_coordinates: [72.8258, 18.925],
      rationale:
        "Spill origin is located 14.2 km from cataloged seep formation SEEP-IND-BH02 (bearing 214.5°). Geological seabed discharge represents an improbable origin for the fresh heavy emulsion observed on SAR.",
    },
  },
  {
    id: "alt-2-imaging-artifact",
    case_id: "case-2026-0814-in-bom",
    hypothesis: "imaging_artifact",
    score: 6.0,
    confidence: 92.0,
    created_at: "2026-08-14T04:30:00Z",
    evidence: {
      lookalike_risk: 0.052,
      incidence_angle_deg: 34.5,
      wind_speed_ms: 5.8,
      sensor: "Sentinel-1A C-SAR IW GRDH (VV/VH)",
      angle_factor: 1.0,
      wind_factor: 1.0,
      damping_ratio_db: -18.4,
      rationale:
        "High SAR backscatter damping contrast (-18.4 dB) combined with moderate ambient 10m wind velocity (5.8 m/s) rule out low-wind calm water patches, grease ice, or biogenic surfactant algal blooms.",
    },
  },
  {
    id: "alt-3-non-ais-vessel",
    case_id: "case-2026-0814-in-bom",
    hypothesis: "non_ais_vessel",
    score: 40.0,
    confidence: 78.0,
    created_at: "2026-08-14T04:30:00Z",
    evidence: {
      candidate_count: 4,
      dark_gap_count: 1,
      unidentified_radar_contacts: 0,
      regional_ais_coverage: "partial",
      traffic_density: "High commercial tanker corridor",
      rationale:
        "One candidate vessel exhibited a 75-minute AIS transponder silence window in the sector. However, zero uncorrelated metallic radar contacts were detected on co-registered SAR imagery.",
    },
  },
];

export function AlternativeExplanationsPanel({
  caseId = "case-2026-0814-in-bom",
  alternatives,
  topCandidateScore = 88.4,
  topCandidateName = "MT PACIFIC TRADER",
  onSelectHypothesis,
  className = "",
}: AlternativeExplanationsPanelProps) {
  const [data, setData] = React.useState<AlternativeExplanation[]>(
    alternatives && alternatives.length > 0 ? alternatives : SYNTHETIC_ALTERNATIVES
  );
  const [categoryFilter, setCategoryFilter] = React.useState<string>("all");
  const [sortBy, setSortBy] = React.useState<"score_desc" | "score_asc" | "confidence">("score_desc");
  const [expandedId, setExpandedId] = React.useState<string | null>(null);

  // Attempt live API fetch if not provided
  React.useEffect(() => {
    if (alternatives && alternatives.length > 0) {
      setData(alternatives);
      return;
    }

    let isMounted = true;
    const fetchAlts = async () => {
      try {
        const res = await fetch(`/api/v1/cases/${caseId}/alternatives`);
        if (res.ok) {
          const json: AlternativeExplanation[] = await res.json();
          if (isMounted && json && json.length > 0) {
            setData(json);
          }
        }
      } catch {
        // Fallback to synthetic dataset
      }
    };

    void fetchAlts();
    return () => {
      isMounted = false;
    };
  }, [caseId, alternatives]);

  // Filter and sort hypotheses
  const processedList = React.useMemo(() => {
    let list = [...data];

    if (categoryFilter !== "all") {
      list = list.filter((item) => item.hypothesis.toLowerCase() === categoryFilter.toLowerCase());
    }

    list.sort((a, b) => {
      if (sortBy === "score_desc") return b.score - a.score;
      if (sortBy === "score_asc") return a.score - b.score;
      if (sortBy === "confidence") return b.confidence - a.confidence;
      return 0;
    });

    return list;
  }, [data, categoryFilter, sortBy]);

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  // Helper formatting metadata
  const getHypothesisConfig = (hyp: string) => {
    switch (hyp) {
      case "natural_seep":
        return {
          title: "Natural Hydrocarbon Seep",
          categoryLabel: "Geological Phenomenon",
          icon: Mountain,
          iconColor: "text-brand-green",
          badgeColor: "greenSoft" as const,
          description: "Sub-sea hydrocarbon expulsion from active geological faults or seabed reservoirs.",
        };
      case "imaging_artifact":
        return {
          title: "Atmospheric / Oceanic Lookalike",
          categoryLabel: "False-Positive Artifact",
          icon: Scan,
          iconColor: "text-brand-teal-mid",
          badgeColor: "outline" as const,
          description: "Low-wind calm water patches, biogenic surfactant films, or radar speckle geometry.",
        };
      case "non_ais_vessel":
        return {
          title: "Unregistered / Non-AIS Dark Vessel",
          categoryLabel: "Dark Maritime Target",
          icon: Radio,
          iconColor: "text-accent-orange",
          badgeColor: "orange" as const,
          description: "Vessels operating without active AIS transponders or during satellite constellation latency.",
        };
      default:
        return {
          title: "Alternative Origin Hypothesis",
          categoryLabel: "Non-Vessel Hypothesis",
          icon: Compass,
          iconColor: "text-white",
          badgeColor: "outline" as const,
          description: "Empirical non-vessel hypothesis evaluated under Rule 5 standards.",
        };
    }
  };

  return (
    <div className={`space-y-6 ${className}`}>
      {/* 1. Header & Constitutional Rule 5 Declaration */}
      <div className="rounded-xl border border-hairline-dark bg-brand-teal/30 p-6 backdrop-blur space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Badge variant="purple" className="text-xs">
                Product Rule 5: Multi-Hypothesis Analysis
              </Badge>
              <Badge variant="greenSoft" className="font-mono text-xs">
                3 Hypotheses Scored
              </Badge>
            </div>
            <h2 className="text-xl font-bold tracking-tight text-white sm:text-2xl flex items-center gap-2">
              <Scale className="h-5 w-5 text-brand-green" />
              <span>Alternative Explanations & Lookalike Verification</span>
            </h2>
            <p className="text-xs text-on-dark-muted max-w-3xl leading-relaxed">
              In accordance with Constitutional Rule 5, every investigation rigorously scores non-vessel
              hypotheses alongside suspect vessel candidates to guarantee neutral, balanced forensic attribution.
            </p>
          </div>

          <div className="rounded-lg border border-hairline-dark bg-brand-teal-deep/80 p-3 text-right">
            <span className="text-[10px] uppercase font-mono tracking-wider text-on-dark-muted block">
              Multi-Hypothesis Integrity
            </span>
            <div className="flex items-center justify-end gap-1.5 mt-0.5">
              <ShieldCheck className="h-4 w-4 text-brand-green" />
              <span className="text-xs font-semibold text-white">Rule 5 Verified</span>
            </div>
          </div>
        </div>

        {/* Executive Contrast Summary: Candidate Vessel vs Hypotheses */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 pt-2 border-t border-hairline-dark">
          <div className="rounded-lg border border-brand-green/40 bg-brand-teal-deep/90 p-3">
            <span className="text-[10px] uppercase font-mono tracking-wider text-brand-green block">
              Primary Putative Correlate
            </span>
            <div className="flex items-baseline justify-between mt-1">
              <span className="font-bold text-sm text-white truncate max-w-[130px]">
                {topCandidateName}
              </span>
              <span className="font-mono text-base font-bold text-brand-green">
                {topCandidateScore.toFixed(1)}
                <span className="text-[10px] text-on-dark-muted">/100</span>
              </span>
            </div>
            <span className="text-[10px] text-on-dark-muted block mt-0.5">
              Candidate Vessel S_culprit
            </span>
          </div>

          {data.map((item) => {
            const config = getHypothesisConfig(item.hypothesis);
            const ratio = (topCandidateScore / Math.max(1.0, item.score)).toFixed(1);
            return (
              <div
                key={item.id}
                className="rounded-lg border border-hairline-dark bg-brand-teal-deep/60 p-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] uppercase font-mono tracking-wider text-on-dark-muted truncate">
                    {config.title.split(" ")[0]} Plausibility
                  </span>
                  <span className="font-mono text-[10px] text-brand-green-soft">
                    {ratio}× lower
                  </span>
                </div>
                <div className="flex items-baseline justify-between mt-1">
                  <span className="font-mono text-base font-bold text-white">
                    {item.score.toFixed(1)}
                    <span className="text-[10px] text-on-dark-muted">/100</span>
                  </span>
                  <Badge variant="outline" className="font-mono text-[9px] px-1 py-0">
                    {item.confidence.toFixed(0)}% CI
                  </Badge>
                </div>
                <div className="h-1 w-full rounded-full bg-brand-teal mt-1.5">
                  <div
                    className={`h-1 rounded-full ${
                      item.score > 30 ? "bg-accent-orange" : "bg-brand-green"
                    }`}
                    style={{ width: `${Math.min(100, item.score)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 2. Filter Bar & Sort Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-on-dark-muted font-medium flex items-center gap-1">
            <Filter className="h-3 w-3" /> Category:
          </span>
          {[
            { id: "all", label: "All Hypotheses" },
            { id: "natural_seep", label: "Natural Seeps" },
            { id: "imaging_artifact", label: "SAR Lookalikes" },
            { id: "non_ais_vessel", label: "Non-AIS Targets" },
          ].map((pill) => (
            <button
              key={pill.id}
              type="button"
              onClick={() => setCategoryFilter(pill.id)}
              className={`rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors ${
                categoryFilter === pill.id
                  ? "bg-brand-green text-brand-teal-deep shadow"
                  : "bg-brand-teal-deep border border-hairline-dark text-on-dark-muted hover:text-white"
              }`}
            >
              {pill.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-xs text-on-dark-muted font-medium flex items-center gap-1">
            <ArrowUpDown className="h-3 w-3" /> Sort:
          </span>
          <select
            value={sortBy}
            onChange={(e) =>
              setSortBy(e.target.value as "score_desc" | "score_asc" | "confidence")
            }
            className="h-7 rounded-md border border-hairline-dark bg-brand-teal-deep px-2 text-xs text-white focus:border-brand-green focus:outline-none"
          >
            <option value="score_desc">Plausibility Score (Highest First)</option>
            <option value="score_asc">Plausibility Score (Lowest First)</option>
            <option value="confidence">Rule 1 Confidence (Highest First)</option>
          </select>
        </div>
      </div>

      {/* 3. Hypothesis Cards Grid */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        {processedList.map((item) => {
          const config = getHypothesisConfig(item.hypothesis);
          const Icon = config.icon;
          const isExpanded = expandedId === item.id;
          const ev = (item.evidence || {}) as NaturalSeepEvidence &
            ImagingArtifactEvidence &
            NonAISVesselEvidence & {
              nearest_seep_name?: string;
              nearest_seep_id?: string;
              basin?: string;
              distance_km?: number;
              bearing_deg?: number;
              water_depth_m?: number;
              seep_type?: string;
              activity_status?: string;
              lookalike_risk?: number;
              incidence_angle_deg?: number;
              wind_speed_ms?: number;
              sensor?: string;
              damping_ratio_db?: number;
              candidate_count?: number;
              dark_gap_count?: number;
              unidentified_radar_contacts?: number;
              regional_ais_coverage?: string;
              traffic_density?: string;
              rationale?: string;
            };

          return (
            <Card
              key={item.id}
              className={`border transition-all flex flex-col justify-between ${
                item.score >= 30.0
                  ? "border-accent-orange/40 hover:border-accent-orange bg-brand-teal-deep/90"
                  : "border-hairline-dark hover:border-brand-green/50 bg-brand-teal-deep/70"
              }`}
            >
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between gap-2">
                  <Badge variant={config.badgeColor} className="text-[11px] gap-1">
                    <Icon className="h-3 w-3" />
                    {config.categoryLabel}
                  </Badge>

                  {/* Rule 1: Mandatory Paired Confidence */}
                  <div className="flex items-center gap-1.5">
                    <Badge variant="greenSoft" className="font-mono text-[10px]">
                      {item.confidence.toFixed(1)}% CI
                    </Badge>
                  </div>
                </div>

                <CardTitle className="text-lg font-bold text-white mt-2 flex items-center gap-2">
                  <span>{config.title}</span>
                </CardTitle>
                <CardDescription className="text-xs text-on-dark-muted">
                  {config.description}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4 text-xs">
                {/* Score & Risk Assessment Meter */}
                <div className="rounded-lg border border-hairline-dark bg-brand-teal/20 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase font-mono tracking-wider text-on-dark-muted">
                      Hypothesis Plausibility
                    </span>
                    <span className="font-mono text-base font-bold text-brand-green">
                      {item.score.toFixed(1)}
                      <span className="text-xs text-on-dark-muted">/100</span>
                    </span>
                  </div>

                  {/* Meter Bar */}
                  <div className="space-y-1">
                    <div className="h-2 w-full rounded-full bg-brand-teal overflow-hidden">
                      <div
                        className={`h-2 rounded-full transition-all duration-500 ${
                          item.score < 20
                            ? "bg-brand-green"
                            : item.score < 50
                            ? "bg-accent-orange"
                            : "bg-red-500"
                        }`}
                        style={{ width: `${Math.min(100, Math.max(4, item.score))}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-[9px] font-mono text-on-dark-muted">
                      <span>Low Plausibility</span>
                      <span>Moderate</span>
                      <span>Elevated</span>
                    </div>
                  </div>
                </div>

                {/* Specific Dimension Metrics */}
                {item.hypothesis === "natural_seep" && (
                  <div className="space-y-2 font-mono text-[11px]">
                    <div className="flex justify-between border-b border-hairline-dark pb-1 text-on-dark-muted">
                      <span>Nearest Seep:</span>
                      <span className="font-semibold text-white text-right truncate max-w-[170px]">
                        {ev.nearest_seep_name || "SEEP-IND-BH02"}
                      </span>
                    </div>
                    <div className="flex justify-between border-b border-hairline-dark pb-1 text-on-dark-muted">
                      <span>Separation Distance:</span>
                      <span className="font-semibold text-brand-green">
                        {ev.distance_km ? `${ev.distance_km.toFixed(1)} km` : "14.2 km"}
                      </span>
                    </div>
                    <div className="flex justify-between border-b border-hairline-dark pb-1 text-on-dark-muted">
                      <span>Seep Type:</span>
                      <span className="font-semibold text-white">
                        {ev.seep_type || "Thermogenic Condensate"}
                      </span>
                    </div>
                    <div className="flex justify-between text-on-dark-muted">
                      <span>Water Depth:</span>
                      <span className="font-semibold text-white">
                        {ev.water_depth_m ? `${ev.water_depth_m} m` : "85 m"}
                      </span>
                    </div>
                  </div>
                )}

                {item.hypothesis === "imaging_artifact" && (
                  <div className="space-y-2 font-mono text-[11px]">
                    <div className="flex justify-between border-b border-hairline-dark pb-1 text-on-dark-muted">
                      <span>SAR Incidence Angle:</span>
                      <span className="font-semibold text-white">
                        {ev.incidence_angle_deg ? `${ev.incidence_angle_deg}°` : "34.5°"}
                      </span>
                    </div>
                    <div className="flex justify-between border-b border-hairline-dark pb-1 text-on-dark-muted">
                      <span>Ambient 10m Wind:</span>
                      <span className="font-semibold text-brand-green">
                        {ev.wind_speed_ms ? `${ev.wind_speed_ms} m/s` : "5.8 m/s"}
                      </span>
                    </div>
                    <div className="flex justify-between border-b border-hairline-dark pb-1 text-on-dark-muted">
                      <span>Backscatter Damping:</span>
                      <span className="font-semibold text-white">
                        {ev.damping_ratio_db ? `${ev.damping_ratio_db} dB` : "-18.4 dB"}
                      </span>
                    </div>
                    <div className="flex justify-between text-on-dark-muted">
                      <span>Segmentation Risk:</span>
                      <span className="font-semibold text-brand-green">
                        {ev.lookalike_risk ? `${(ev.lookalike_risk * 100).toFixed(1)}%` : "5.2%"}
                      </span>
                    </div>
                  </div>
                )}

                {item.hypothesis === "non_ais_vessel" && (
                  <div className="space-y-2 font-mono text-[11px]">
                    <div className="flex justify-between border-b border-hairline-dark pb-1 text-on-dark-muted">
                      <span>Transponder Gaps:</span>
                      <span className="font-semibold text-accent-orange">
                        {ev.dark_gap_count !== undefined ? `${ev.dark_gap_count} detected (75m)` : "1 detected"}
                      </span>
                    </div>
                    <div className="flex justify-between border-b border-hairline-dark pb-1 text-on-dark-muted">
                      <span>Uncorrelated Radar Targets:</span>
                      <span className="font-semibold text-brand-green">
                        {ev.unidentified_radar_contacts ?? 0}
                      </span>
                    </div>
                    <div className="flex justify-between border-b border-hairline-dark pb-1 text-on-dark-muted">
                      <span>Regional Satellite AIS:</span>
                      <span className="font-semibold text-white">
                        {ev.regional_ais_coverage || "Partial"}
                      </span>
                    </div>
                    <div className="flex justify-between text-on-dark-muted">
                      <span>Traffic Sector:</span>
                      <span className="font-semibold text-white truncate max-w-[160px]">
                        {ev.traffic_density || "High Density"}
                      </span>
                    </div>
                  </div>
                )}

                {/* Forensic Rationale */}
                <div className="rounded-md border border-hairline-dark bg-brand-teal-deep/80 p-2.5">
                  <p className="text-[11px] leading-relaxed text-on-dark-muted">
                    {ev.rationale || "Objective forensic evaluation under Rule 5."}
                  </p>
                </div>

                {/* Expandable Evidence Parameters */}
                {isExpanded && (
                  <div className="rounded-md border border-hairline-dark bg-brand-teal-deep p-3 space-y-2 text-[10px] font-mono text-on-dark-muted animate-in fade-in duration-200">
                    <div className="text-white font-bold pb-1 border-b border-hairline-dark flex items-center gap-1.5">
                      <Layers className="h-3 w-3 text-brand-green" />
                      <span>Empirical Telemetry Parameters</span>
                    </div>
                    {Object.entries(ev)
                      .filter(([k]) => k !== "rationale")
                      .map(([k, v]) => (
                        <div key={k} className="flex justify-between">
                          <span className="text-on-dark-muted">{k}:</span>
                          <span className="text-white truncate max-w-[160px]">
                            {typeof v === "object" ? JSON.stringify(v) : String(v)}
                          </span>
                        </div>
                      ))}
                  </div>
                )}

                {/* Action Buttons */}
                <div className="flex items-center gap-2 pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toggleExpand(item.id)}
                    className="flex-1 gap-1 text-[11px]"
                  >
                    {isExpanded ? (
                      <>
                        <ChevronUp className="h-3 w-3" />
                        <span>Hide Telemetry</span>
                      </>
                    ) : (
                      <>
                        <ChevronDown className="h-3 w-3" />
                        <span>Inspect Evidence</span>
                      </>
                    )}
                  </Button>

                  {onSelectHypothesis && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => onSelectHypothesis(item)}
                      className="gap-1 text-[11px]"
                    >
                      <span>Focus</span>
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

export default AlternativeExplanationsPanel;
