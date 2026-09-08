"use client";

import * as React from "react";
import {
  Search,
  Filter,
  ArrowUpDown,
  Anchor,
  ShieldCheck,
  AlertCircle,
} from "lucide-react";

import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { VesselCandidateCard } from "./VesselCandidateCard";
import type { VesselCandidate } from "@/types";

export const SYNTHETIC_CANDIDATES: VesselCandidate[] = [
  {
    id: "cand-1-pacific-trader",
    case_id: "case-20260814-in-bom",
    mmsi: 419001234,
    imo: 9283741,
    name: "MT PACIFIC TRADER",
    flag_state: "Panama",
    vessel_type: "Crude Oil Tanker",
    s_culprit: 0.884,
    confidence: 91.4,
    ais_coverage: "full",
    anomaly_flags: ["speed_drop_dumping"],
    sub_scores: {
      spatial: 94.2,
      temporal: 89.0,
      kinematic: 84.5,
      anomaly: 76.0,
      type: 95.0,
    },
    created_at: "2026-08-14T04:00:00Z",
  },
  {
    id: "cand-2-arabian-gulf",
    case_id: "case-20260814-in-bom",
    mmsi: 470123456,
    imo: 9345678,
    name: "MV ARABIAN GULF",
    flag_state: "United Arab Emirates",
    vessel_type: "Product Tanker",
    s_culprit: 0.612,
    confidence: 78.0,
    ais_coverage: "dark_gap",
    anomaly_flags: ["dark_transponder_gap", "loitering_at_origin"],
    sub_scores: {
      spatial: 72.0,
      temporal: 65.0,
      kinematic: 60.0,
      anomaly: 85.0,
      type: 90.0,
    },
    created_at: "2026-08-14T04:00:00Z",
  },
  {
    id: "cand-3-ocean-star",
    case_id: "case-20260814-in-bom",
    mmsi: 563004567,
    imo: 9451234,
    name: "MV OCEAN STAR",
    flag_state: "Singapore",
    vessel_type: "Container Ship",
    s_culprit: 0.541,
    confidence: 88.0,
    ais_coverage: "full",
    anomaly_flags: [],
    sub_scores: {
      spatial: 68.0,
      temporal: 55.4,
      kinematic: 50.2,
      anomaly: 35.0,
      type: 62.0,
    },
    created_at: "2026-08-14T04:00:00Z",
  },
  {
    id: "cand-4-seabird-explorer",
    case_id: "case-20260814-in-bom",
    mmsi: 412998877,
    imo: 9128833,
    name: "SEABIRD EXPLORER",
    flag_state: "India",
    vessel_type: "Offshore Supply",
    s_culprit: 0.219,
    confidence: 82.5,
    ais_coverage: "full",
    anomaly_flags: [],
    sub_scores: {
      spatial: 34.5,
      temporal: 22.0,
      kinematic: 28.0,
      anomaly: 15.0,
      type: 40.0,
    },
    created_at: "2026-08-14T04:00:00Z",
  },
];

export interface VesselRankingListProps {
  candidates?: VesselCandidate[];
  selectedMmsi?: number | null;
  onSelectCandidate?: (candidate: VesselCandidate) => void;
  onInspectTrack?: (candidate: VesselCandidate) => void;
  onOpenExplainability?: (candidate: VesselCandidate) => void;
  className?: string;
}

export function VesselRankingList({
  candidates,
  selectedMmsi,
  onSelectCandidate,
  onInspectTrack,
  onOpenExplainability,
  className = "",
}: VesselRankingListProps) {
  const [searchQuery, setSearchQuery] = React.useState<string>("");
  const [coverageFilter, setCoverageFilter] = React.useState<string>("all");
  const [sortBy, setSortBy] = React.useState<"score" | "spatial" | "temporal">("score");

  // Fallback to realistic synthetic candidates if not provided or empty
  const rawList = React.useMemo(() => {
    return candidates && candidates.length > 0 ? candidates : SYNTHETIC_CANDIDATES;
  }, [candidates]);

  // Filtering
  const filteredList = React.useMemo(() => {
    return rawList.filter((vessel) => {
      const matchesSearch =
        searchQuery.trim() === "" ||
        vessel.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        String(vessel.mmsi).includes(searchQuery) ||
        (vessel.flag_state?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false) ||
        vessel.vessel_type.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesCoverage =
        coverageFilter === "all" || vessel.ais_coverage.toLowerCase() === coverageFilter.toLowerCase();

      return matchesSearch && matchesCoverage;
    });
  }, [rawList, searchQuery, coverageFilter]);

  // Sorting
  const sortedList = React.useMemo(() => {
    const list = [...filteredList];
    list.sort((a, b) => {
      if (sortBy === "spatial") {
        return (b.sub_scores?.spatial ?? 0) - (a.sub_scores?.spatial ?? 0);
      }
      if (sortBy === "temporal") {
        return (b.sub_scores?.temporal ?? 0) - (a.sub_scores?.temporal ?? 0);
      }
      return b.s_culprit - a.s_culprit;
    });
    return list;
  }, [filteredList, sortBy]);

  const topCandidate = sortedList[0];

  return (
    <div className={`space-y-6 ${className}`} data-testid="vessel-ranking-list">
      {/* 1. Header Strip: Search, Filter, Sort & Rule 1 / Rule 6 Compliance Banner */}
      <div className="flex flex-col gap-4 rounded-xl border border-hairline-dark bg-brand-teal-deep/90 p-4 shadow-xl backdrop-blur">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Anchor className="h-5 w-5 text-brand-green" />
              <h3 className="text-lg font-bold text-white">Candidate Suspect Vessel Rankings</h3>
            </div>
            <p className="text-xs text-on-dark-muted mt-0.5">
              Multi-criteria AHP attribution combining backward dispersion covariance, AIS kinematics, and transponder consistency.
            </p>
          </div>

          {topCandidate && (
            <div className="flex items-center gap-2">
              <Badge variant="green" className="text-xs font-mono">
                Top Candidate: {topCandidate.name} (S: {topCandidate.s_culprit <= 1 ? topCandidate.s_culprit.toFixed(3) : (topCandidate.s_culprit / 100).toFixed(3)})
              </Badge>
              <div className="flex items-center gap-1.5 rounded-lg border border-brand-green/30 bg-brand-green/10 px-2.5 py-1 font-mono text-xs text-brand-green">
                <ShieldCheck className="h-3.5 w-3.5 text-brand-green" />
                <span>{topCandidate.confidence.toFixed(1)}% CI</span>
              </div>
            </div>
          )}
        </div>

        {/* Controls Bar */}
        <div className="flex flex-col gap-3 pt-3 border-t border-hairline-dark sm:flex-row sm:items-center sm:justify-between">
          {/* Search Input */}
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-on-dark-muted" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter by vessel name, MMSI, flag, or type..."
              className="pl-9 text-xs"
            />
          </div>

          {/* Filter & Sort Controls */}
          <div className="flex flex-wrap items-center gap-3">
            {/* AIS Coverage Filter Pills */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-on-dark-muted font-medium flex items-center gap-1">
                <Filter className="h-3 w-3" /> AIS:
              </span>
              {[
                { id: "all", label: "All" },
                { id: "full", label: "Continuous" },
                { id: "dark_gap", label: "Transponder Gaps" },
              ].map((pill) => (
                <button
                  key={pill.id}
                  type="button"
                  onClick={() => setCoverageFilter(pill.id)}
                  className={`rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors ${
                    coverageFilter === pill.id
                      ? "bg-brand-green text-brand-teal-deep shadow"
                      : "bg-brand-teal-deep border border-hairline-dark text-on-dark-muted hover:text-white"
                  }`}
                >
                  {pill.label}
                </button>
              ))}
            </div>

            {/* Sort Selector */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-on-dark-muted font-medium flex items-center gap-1">
                <ArrowUpDown className="h-3 w-3" /> Sort:
              </span>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as "score" | "spatial" | "temporal")}
                className="h-7 rounded-md border border-hairline-dark bg-brand-teal-deep px-2 text-xs text-white focus:border-brand-green focus:outline-none"
              >
                <option value="score">Attribution Score (Highest First)</option>
                <option value="spatial">Spatial Proximity (CPA)</option>
                <option value="temporal">Temporal Proximity (&Delta;t)</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Candidate Cards Grid */}
      {sortedList.length === 0 ? (
        <div className="rounded-xl border border-hairline-dark bg-brand-teal-deep/50 p-12 text-center text-sm text-on-dark-muted font-mono">
          <AlertCircle className="mx-auto h-8 w-8 text-on-dark-muted mb-2" />
          No candidate vessels match the current search or filter criteria.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {sortedList.map((candidate, index) => (
            <VesselCandidateCard
              key={candidate.mmsi}
              candidate={candidate}
              rank={index + 1}
              isSelected={selectedMmsi === candidate.mmsi}
              onSelect={onSelectCandidate}
              onInspectTrack={onInspectTrack}
              onOpenExplainability={onOpenExplainability}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default VesselRankingList;
