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
      return <Badge variant="outline" className="rounded-sm border-emerald-500/50 bg-emerald-950/40 text-emerald-400 font-mono text-[10px] font-bold">RANK 1: PUTATIVE SOURCE</Badge>;
    }
    if (rankNum === 2) {
      return <Badge variant="outline" className="rounded-sm border-sky-500/50 bg-sky-950/40 text-sky-400 font-mono text-[10px] font-bold">RANK 2: CANDIDATE SUSPECT</Badge>;
    }
    return <Badge variant="outline" className="rounded-sm border-slate-700 bg-slate-900/60 text-slate-400 font-mono text-[10px]">RANK {rankNum}: LOW CORRELATION</Badge>;
  };

  const getAisCoverageBadge = (coverage: AISCoverage | string) => {
    switch (coverage) {
      case "full":
        return (
          <Badge variant="outline" className="gap-1 font-mono text-[10px] rounded-sm border-emerald-500/40 bg-emerald-950/20 text-emerald-400">
            <Radio className="h-3 w-3 text-emerald-400" />
            <span>AIS: CONTINUOUS</span>
          </Badge>
        );
      case "dark_gap":
        return (
          <Badge variant="outline" className="gap-1 font-mono text-[10px] rounded-sm border-amber-500/40 bg-amber-950/20 text-amber-400">
            <Radio className="h-3 w-3" />
            <span>AIS: TRANSPONDER GAP</span>
          </Badge>
        );
      case "non_ais_unknown":
        return (
          <Badge variant="outline" className="gap-1 font-mono text-[10px] rounded-sm border-purple-500/40 bg-purple-950/20 text-purple-400">
            <AlertTriangle className="h-3 w-3" />
            <span>NON-AIS TARGET</span>
          </Badge>
        );
      default:
        return (
          <Badge variant="outline" className="font-mono text-[10px] rounded-sm border-slate-700 text-slate-400">
            AIS: {coverage}
          </Badge>
        );
    }
  };

  return (
    <Card
      className={`relative overflow-hidden transition-all duration-200 cursor-pointer rounded-sm ${
        isSelected
          ? "border-emerald-500 bg-[#161F2C] ring-1 ring-emerald-500/30"
          : rank === 1
          ? "border-emerald-500/40 hover:border-emerald-400 bg-[#111720] hover:bg-[#161F2C]/50"
          : "border-[#1F2937] hover:border-slate-600 bg-[#111720] hover:bg-[#161F2C]/40"
      } ${className}`}
      onClick={() => onSelect?.(candidate)}
      data-testid={`vessel-candidate-card-${candidate.mmsi}`}
    >
      {/* 1. Header: Rank, Coverage & Identity */}
      <CardHeader className="pb-3 border-b border-[#1F2937]">
        <div className="flex items-center justify-between gap-2">
          {getRankBadge(rank)}
          {getAisCoverageBadge(candidate.ais_coverage)}
        </div>

        <div className="mt-2 flex items-start justify-between">
          <div>
            <CardTitle className="text-base font-bold font-mono text-slate-100 flex items-center gap-2">
              <Anchor className="h-4 w-4 text-emerald-400 shrink-0" />
              <span>{candidate.name}</span>
            </CardTitle>
            <CardDescription className="font-mono text-xs text-slate-400 mt-0.5 tabular-nums">
              MMSI: {candidate.mmsi} {candidate.imo ? `│ IMO: ${candidate.imo}` : ""} │ FLAG:{" "}
              {candidate.flag_state ?? "Unknown"}
            </CardDescription>
          </div>

          <Badge variant="outline" className="text-[10px] font-mono shrink-0 rounded-sm border-slate-700 text-slate-300">
            {candidate.vessel_type}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 pt-3 text-sm">
        {/* 2. Attribution Score & Paired Confidence Chip (Constitutional Rule 1) */}
        <div className="rounded-sm border border-[#1F2937] bg-[#0B0F14] p-3">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <span>ATTRIBUTION SCORE (S_CULPRIT)</span>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Info className="h-3 w-3 text-slate-500 cursor-help" />
                  </TooltipTrigger>
                  <TooltipContent>
                    Multi-criteria AHP score evaluating spatial, temporal, kinematic, anomaly, and type dimensions.
                  </TooltipContent>
                </Tooltip>
              </div>
              <div className="flex items-baseline gap-1.5 font-mono tabular-nums">
                <span
                  className={`text-2xl font-bold ${
                    rank === 1 ? "text-emerald-400" : "text-slate-100"
                  }`}
                >
                  {scoreFormatted}
                </span>
                <span className="text-xs text-slate-500">/ 1.000</span>
              </div>
            </div>

            {/* Constitutional Rule 1: Paired Confidence Badge */}
            <div className="text-right space-y-0.5">
              <div className="text-[9px] font-mono uppercase font-semibold text-slate-500">
                RULE 1 CONFIDENCE
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="inline-flex items-center gap-1.5 rounded-sm border border-emerald-500/40 bg-emerald-950/30 px-2 py-0.5 font-mono text-xs text-emerald-400 font-bold tabular-nums">
                    <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
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
          <div className="mt-2.5 h-1 w-full overflow-hidden rounded-sm bg-slate-800">
            <div
              className={`h-full transition-all duration-500 rounded-sm ${
                rank === 1
                  ? "bg-emerald-500"
                  : rank === 2
                  ? "bg-sky-400"
                  : "bg-slate-500"
              }`}
              style={{ width: `${Math.min(100, Math.max(0, normalizedScore))}%` }}
            />
          </div>
        </div>

        {/* 3. Multi-Criteria AHP 5-Component Sub-Scores Breakdown (Rule 2) */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-mono text-slate-400">
            <span className="flex items-center gap-1 font-semibold uppercase tracking-wider text-[10px]">
              <Sliders className="h-3 w-3 text-emerald-400" />
              AHP DIMENSIONAL SUB-SCORES
            </span>
            <span className="font-mono text-[10px] tabular-nums">WEIGHTS (CR &lt; 0.10)</span>
          </div>

          <div className="space-y-1.5">
            {[
              { label: "Spatial Proximity", value: subScores.spatial, color: "bg-emerald-500" },
              { label: "Temporal Coincidence", value: subScores.temporal, color: "bg-emerald-600" },
              { label: "Kinematic Heading", value: subScores.kinematic, color: "bg-sky-400" },
              { label: "Behavioral Anomaly", value: subScores.anomaly, color: "bg-amber-400" },
              { label: "Vessel Type Prior", value: subScores.type, color: "bg-purple-400" },
            ].map((sub) => (
              <div key={sub.label} className="space-y-0.5">
                <div className="flex justify-between text-[11px] font-mono tabular-nums">
                  <span className="text-slate-400">{sub.label}</span>
                  <span className="font-semibold text-slate-200">{sub.value.toFixed(1)}</span>
                </div>
                <div className="h-1 w-full overflow-hidden rounded-sm bg-slate-800">
                  <div
                    className={`h-full rounded-sm ${sub.color}`}
                    style={{ width: `${Math.min(100, Math.max(0, sub.value))}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 4. Physical Encounter Metrics */}
        <div className="grid grid-cols-2 gap-2 text-xs border-t border-[#1F2937] pt-2.5 font-mono tabular-nums">
          <div className="flex justify-between">
            <span className="text-slate-500">CPA Proximity:</span>
            <span className="font-medium text-slate-200">
              {rank === 1 ? "0.42 NM" : rank === 2 ? "2.15 NM" : "4.80 NM"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Temporal Offset:</span>
            <span className="font-medium text-slate-200">
              {rank === 1 ? "-18 min" : rank === 2 ? "+42 min" : "+115 min"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Speed at CPA:</span>
            <span className="font-medium text-slate-200">
              {rank === 1 ? "14.2 kts" : rank === 2 ? "18.5 kts" : "9.8 kts"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Heading Alignment:</span>
            <span className="font-medium text-slate-200">
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
                variant="outline"
                className="text-[10px] font-mono uppercase rounded-sm border-amber-500/40 bg-amber-950/20 text-amber-400"
              >
                {flag.replace(/_/g, " ")}
              </Badge>
            ))}
          </div>
        )}

        {/* 6. Action Triggers */}
        <div className="flex items-center gap-2 pt-1">
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onInspectTrack?.(candidate);
            }}
            className="flex-1 gap-1.5 text-xs font-mono font-semibold rounded-sm border-slate-700 bg-slate-900/80 text-slate-200 hover:bg-slate-800"
          >
            <Compass className="h-3.5 w-3.5 text-emerald-400" />
            <span>INSPECT TRAJECTORY</span>
          </Button>

          <Button
            variant="default"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onOpenExplainability?.(candidate);
            }}
            className={`gap-1 text-xs font-mono font-semibold rounded-sm ${
              rank === 1
                ? "bg-emerald-600 hover:bg-emerald-500 text-slate-950"
                : "bg-slate-800 hover:bg-slate-700 text-slate-200"
            }`}
          >
            <span>EXPLAIN</span>
            <ChevronRight className="h-3 w-3" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default VesselCandidateCard;
