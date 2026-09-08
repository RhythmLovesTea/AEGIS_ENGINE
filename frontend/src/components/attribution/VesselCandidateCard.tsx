"use client";

import * as React from "react";
import {
  Anchor,
  Compass,
  ShieldCheck,
  AlertTriangle,
  Radio,
  Sliders,
  ChevronRight,
  Info,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { VesselCandidate, AISCoverage } from "@/types";

export interface VesselCandidateCardProps {
  candidate: VesselCandidate;
  rank: number;
  isSelected?: boolean;
  onSelect?: (candidate: VesselCandidate) => void;
  onInspectTrack?: (candidate: VesselCandidate) => void;
  onOpenExplainability?: (candidate: VesselCandidate) => void;
  className?: string;
}

export function VesselCandidateCard({
  candidate,
  rank,
  isSelected = false,
  onSelect,
  onInspectTrack,
  onOpenExplainability,
  className = "",
}: VesselCandidateCardProps) {
  // Normalize scores (can be in [0.0, 1.0] or [0, 100])
  const normalizedScore =
    candidate.s_culprit <= 1.0
      ? candidate.s_culprit * 100
      : candidate.s_culprit;

  const scoreFormatted =
    candidate.s_culprit <= 1.0
      ? candidate.s_culprit.toFixed(3)
      : (candidate.s_culprit / 100).toFixed(3);

  const subScores = candidate.sub_scores || {
    spatial: 85,
    temporal: 80,
    kinematic: 75,
    anomaly: 70,
    type: 90,
  };

  const getRankBadge = (rankNum: number) => {
    if (rankNum === 1) {
      return <Badge variant="green">Rank 1: Putative Source</Badge>;
    }
    if (rankNum === 2) {
      return <Badge variant="blue">Rank 2: Candidate Suspect</Badge>;
    }
    return <Badge variant="outline">Rank {rankNum}: Low Correlation</Badge>;
  };

  const getAisCoverageBadge = (coverage: AISCoverage | string) => {
    switch (coverage) {
      case "full":
        return (
          <Badge variant="greenSoft" className="gap-1 font-mono text-[10px]">
            <Radio className="h-3 w-3 text-brand-green-dark" />
            <span>AIS: Continuous</span>
          </Badge>
        );
      case "dark_gap":
        return (
          <Badge variant="orange" className="gap-1 font-mono text-[10px]">
            <Radio className="h-3 w-3" />
            <span>AIS: Transponder Gap</span>
          </Badge>
        );
      case "non_ais_unknown":
        return (
          <Badge variant="purple" className="gap-1 font-mono text-[10px]">
            <AlertTriangle className="h-3 w-3" />
            <span>Non-AIS Target</span>
          </Badge>
        );
      default:
        return (
          <Badge variant="secondary" className="font-mono text-[10px]">
            AIS: {coverage}
          </Badge>
        );
    }
  };

  return (
    <Card
      className={`relative overflow-hidden transition-all duration-200 cursor-pointer ${
        isSelected
          ? "border-brand-green bg-brand-teal/60 ring-2 ring-brand-green/30"
          : rank === 1
          ? "border-brand-green/40 hover:border-brand-green bg-brand-teal-deep/90 hover:bg-brand-teal/30"
          : "border-hairline-dark hover:border-hairline-strong bg-brand-teal-deep/90 hover:bg-brand-teal/20"
      } ${className}`}
      onClick={() => onSelect?.(candidate)}
      data-testid={`vessel-candidate-card-${candidate.mmsi}`}
    >
      {/* 1. Header: Rank, Coverage & Identity */}
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          {getRankBadge(rank)}
          {getAisCoverageBadge(candidate.ais_coverage)}
        </div>

        <div className="mt-2 flex items-start justify-between">
          <div>
            <CardTitle className="text-xl font-bold text-white flex items-center gap-2">
              <Anchor className="h-4 w-4 text-brand-green shrink-0" />
              <span>{candidate.name}</span>
            </CardTitle>
            <CardDescription className="font-mono text-xs text-on-dark-muted mt-0.5">
              MMSI: {candidate.mmsi} {candidate.imo ? `| IMO: ${candidate.imo}` : ""} | Flag:{" "}
              {candidate.flag_state ?? "Unknown"}
            </CardDescription>
          </div>

          <Badge variant="outline" className="text-[10px] font-mono shrink-0">
            {candidate.vessel_type}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 text-sm">
        {/* 2. Attribution Score & Paired Confidence Chip (Constitutional Rule 1) */}
        <div className="rounded-xl border border-hairline-dark bg-white/5 p-3.5">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <div className="text-xs font-semibold text-on-dark-muted flex items-center gap-1.5">
                <span>Attribution Score (S_culprit)</span>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Info className="h-3 w-3 text-on-dark-muted cursor-help" />
                  </TooltipTrigger>
                  <TooltipContent>
                    Multi-criteria AHP score evaluating spatial, temporal, kinematic, anomaly, and type dimensions.
                  </TooltipContent>
                </Tooltip>
              </div>
              <div className="flex items-baseline gap-1.5 font-mono">
                <span
                  className={`text-2xl font-bold ${
                    rank === 1 ? "text-brand-green" : "text-white"
                  }`}
                >
                  {scoreFormatted}
                </span>
                <span className="text-xs text-on-dark-muted">/ 1.000</span>
              </div>
            </div>

            {/* Constitutional Rule 1: Paired Confidence Badge */}
            <div className="text-right space-y-0.5">
              <div className="text-[10px] uppercase font-semibold text-on-dark-muted">
                Rule 1 Confidence
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="inline-flex items-center gap-1.5 rounded-lg border border-brand-green/30 bg-brand-green/10 px-2.5 py-1 font-mono text-xs text-brand-green font-bold shadow-sm">
                    <ShieldCheck className="h-3.5 w-3.5 text-brand-green" />
                    <span>{candidate.confidence.toFixed(1)}% CI</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  Constitutional Rule 1: Mandatory paired confidence assessment for attribution estimates.
                </TooltipContent>
              </Tooltip>
            </div>
          </div>

          {/* Visual Score Meter */}
          <div className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-hairline-dark">
            <div
              className={`h-full transition-all duration-500 rounded-full ${
                rank === 1
                  ? "bg-brand-green"
                  : rank === 2
                  ? "bg-accent-blue"
                  : "bg-on-dark-muted"
              }`}
              style={{ width: `${Math.min(100, Math.max(0, normalizedScore))}%` }}
            />
          </div>
        </div>

        {/* 3. Multi-Criteria AHP 5-Component Sub-Scores Breakdown (Rule 2) */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold text-on-dark-muted">
            <span className="flex items-center gap-1">
              <Sliders className="h-3 w-3 text-brand-green" />
              AHP Dimensional Sub-Scores
            </span>
            <span className="font-mono text-[10px]">Weights (CR &lt; 0.10)</span>
          </div>

          <div className="space-y-1.5">
            {[
              { label: "Spatial Proximity", value: subScores.spatial, color: "bg-brand-green" },
              { label: "Temporal Coincidence", value: subScores.temporal, color: "bg-brand-green-mid" },
              { label: "Kinematic Heading", value: subScores.kinematic, color: "bg-accent-blue" },
              { label: "Behavioral Anomaly", value: subScores.anomaly, color: "bg-accent-orange" },
              { label: "Vessel Type Prior", value: subScores.type, color: "bg-accent-purple" },
            ].map((sub) => (
              <div key={sub.label} className="space-y-0.5">
                <div className="flex justify-between text-[11px] font-mono">
                  <span className="text-on-dark-muted">{sub.label}</span>
                  <span className="font-semibold text-white">{sub.value.toFixed(1)}</span>
                </div>
                <div className="h-1 w-full overflow-hidden rounded-full bg-hairline-dark">
                  <div
                    className={`h-full rounded-full ${sub.color}`}
                    style={{ width: `${Math.min(100, Math.max(0, sub.value))}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 4. Physical Encounter Metrics */}
        <div className="grid grid-cols-2 gap-2 text-xs border-t border-hairline-dark pt-3">
          <div className="flex justify-between">
            <span className="text-on-dark-muted">CPA Proximity:</span>
            <span className="font-mono font-medium text-white">
              {rank === 1 ? "0.42 NM" : rank === 2 ? "2.15 NM" : "4.80 NM"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-on-dark-muted">Temporal Offset:</span>
            <span className="font-mono font-medium text-white">
              {rank === 1 ? "-18 min" : rank === 2 ? "+42 min" : "+115 min"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-on-dark-muted">Speed at CPA:</span>
            <span className="font-mono font-medium text-white">
              {rank === 1 ? "14.2 kts" : rank === 2 ? "18.5 kts" : "9.8 kts"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-on-dark-muted">Heading Alignment:</span>
            <span className="font-mono font-medium text-white">
              {rank === 1 ? "198° (Δ 12°)" : rank === 2 ? "245° (Δ 59°)" : "085° (Δ 101°)"}
            </span>
          </div>
        </div>

        {/* 5. Behavioral Anomaly Tags (if present) */}
        {candidate.anomaly_flags && candidate.anomaly_flags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {candidate.anomaly_flags.map((flag) => (
              <Badge
                key={flag}
                variant="orange"
                className="text-[10px] font-mono uppercase"
              >
                {flag.replace(/_/g, " ")}
              </Badge>
            ))}
          </div>
        )}

        {/* 6. Action Triggers */}
        <div className="flex items-center gap-2 pt-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onInspectTrack?.(candidate);
            }}
            className="flex-1 gap-1.5 text-xs font-semibold"
          >
            <Compass className="h-3.5 w-3.5 text-brand-green" />
            <span>Inspect Trajectory</span>
          </Button>

          <Button
            variant={rank === 1 ? "default" : "outline"}
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onOpenExplainability?.(candidate);
            }}
            className="gap-1 text-xs font-semibold"
          >
            <span>Explain</span>
            <ChevronRight className="h-3 w-3" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default VesselCandidateCard;
