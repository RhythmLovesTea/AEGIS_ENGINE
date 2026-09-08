"use client";

import * as React from "react";
import Link from "next/link";
import {
  Search,
  Filter,
  ArrowUpDown,
  Radar,
  Clock,
  MapPin,
  Anchor,
  ChevronRight,
  Eye,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SarChipModal } from "./SarChipModal";
import type { CaseDetail } from "@/types";

export interface CaseTableItem {
  id: string;
  referenceCode: string;
  regionName: string;
  coordinates: [number, number]; // [lon, lat]
  sensor: string;
  sceneRef: string;
  detectionTime: string;
  areaKm2: number;
  volumeM3?: number;
  status: "ready" | "hindcasting" | "detecting" | "closed" | string;
  topCandidate?: {
    name: string;
    mmsi: string;
    score: number; // S_culprit
    confidencePct: number;
    flag: string;
  } | null;
}

export const SYNTHETIC_CASES: CaseTableItem[] = [
  {
    id: "case-20260814-in-bom",
    referenceCode: "CASE-2026-0814-IN-BOM",
    regionName: "Offshore Mumbai High Corridor (India EEZ)",
    coordinates: [72.8258, 18.925],
    sensor: "Sentinel-1A C-SAR IW",
    sceneRef: "S1A_IW_GRDH_1SDV_20260814T034215_045123_055678_B42A",
    detectionTime: "2026-08-14T03:42:00Z",
    areaKm2: 5.24,
    volumeM3: 1048,
    status: "ready",
    topCandidate: {
      name: "MT PACIFIC TRADER",
      mmsi: "419001234",
      score: 0.884,
      confidencePct: 91.4,
      flag: "Panama",
    },
  },
  {
    id: "case-20260812-my-mal",
    referenceCode: "CASE-2026-0812-MY-MAL",
    regionName: "Strait of Malacca TSS Corridor (Southeast Asia)",
    coordinates: [102.15, 2.45],
    sensor: "Sentinel-1A C-SAR IW",
    sceneRef: "S1A_IW_GRDH_1SDV_20260812T101530_044990_055412_C11E",
    detectionTime: "2026-08-12T10:15:00Z",
    areaKm2: 3.12,
    volumeM3: 624,
    status: "ready",
    topCandidate: {
      name: "MV STAR ORION",
      mmsi: "563001890",
      score: 0.762,
      confidencePct: 88.5,
      flag: "Singapore",
    },
  },
  {
    id: "case-20260810-uk-eng",
    referenceCode: "CASE-2026-0810-UK-ENG",
    regionName: "English Channel Separation Scheme (Europe)",
    coordinates: [-0.25, 50.15],
    sensor: "Sentinel-1B C-SAR IW",
    sceneRef: "S1B_IW_GRDH_1SDV_20260810T174510_044870_055201_A88F",
    detectionTime: "2026-08-10T17:45:00Z",
    areaKm2: 1.85,
    volumeM3: 370,
    status: "hindcasting",
    topCandidate: null,
  },
  {
    id: "case-20260808-om-hzm",
    referenceCode: "CASE-2026-0808-OM-HZM",
    regionName: "Persian Gulf Strait of Hormuz (Middle East)",
    coordinates: [56.12, 26.25],
    sensor: "Sentinel-1A C-SAR IW",
    sceneRef: "S1A_IW_GRDH_1SDV_20260808T023045_044710_055010_D33B",
    detectionTime: "2026-08-08T02:30:00Z",
    areaKm2: 7.4,
    volumeM3: 1480,
    status: "detecting",
    topCandidate: null,
  },
  {
    id: "case-20260805-us-gom",
    referenceCode: "CASE-2026-0805-US-GOM",
    regionName: "Gulf of Mexico Mississippi Canyon (US EEZ)",
    coordinates: [-89.5, 28.5],
    sensor: "Sentinel-2 MSI Optical",
    sceneRef: "S2A_MSIL2A_20260805T162841_N0500_R083_T16RBT",
    detectionTime: "2026-08-05T16:28:00Z",
    areaKm2: 4.6,
    volumeM3: 920,
    status: "ready",
    topCandidate: {
      name: "MV GULF VANGUARD",
      mmsi: "367123987",
      score: 0.815,
      confidencePct: 89.0,
      flag: "Liberia",
    },
  },
];

export interface CaseTableProps {
  initialCases?: CaseDetail[];
  onSelectCase?: (caseItem: CaseTableItem) => void;
  className?: string;
}

export function CaseTable({
  initialCases,
  onSelectCase,
  className = "",
}: CaseTableProps) {
  // Search & Filter State
  const [searchQuery, setSearchQuery] = React.useState<string>("");
  const [statusFilter, setStatusFilter] = React.useState<string>("all");
  const [sortBy, setSortBy] = React.useState<"recency" | "area" | "score">("recency");
  const [sortOrder, setSortOrder] = React.useState<"asc" | "desc">("desc");

  // Selected SAR Chip preview modal state
  const [selectedChipCase, setSelectedChipCase] = React.useState<CaseTableItem | null>(null);

  // Normalize cases between backend API model and table items
  const cases: CaseTableItem[] = React.useMemo(() => {
    if (!initialCases || initialCases.length === 0) {
      return SYNTHETIC_CASES;
    }

    return initialCases.map((c, index) => {
      const firstDet = c.detections?.[0];
      const area = firstDet ? firstDet.area_m2 / 1_000_000 : 5.0;
      const topCand = c.vessel_candidates?.[0];

      return {
        id: c.id,
        referenceCode: `CASE-${c.id.substring(0, 8).toUpperCase()}`,
        regionName: `Incident Surveillance Zone #${index + 1}`,
        coordinates: [72.8258, 18.925],
        sensor: firstDet?.sensor ?? "Sentinel-1A C-SAR IW",
        sceneRef: c.source_scene_ref ?? "S1A_IW_GRDH_PRODUCT",
        detectionTime: firstDet?.detection_time ?? c.created_at,
        areaKm2: Number(area.toFixed(2)),
        volumeM3: Math.round(area * 200),
        status: c.status,
        topCandidate: topCand
          ? {
              name: topCand.name,
              mmsi: String(topCand.mmsi),
              score: topCand.s_culprit,
              confidencePct: topCand.confidence,
              flag: topCand.flag_state ?? "Panama",
            }
          : null,
      };
    });
  }, [initialCases]);

  // Filtering & Search
  const filteredCases = React.useMemo(() => {
    return cases.filter((item) => {
      const matchesSearch =
        searchQuery.trim() === "" ||
        item.referenceCode.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.regionName.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.sensor.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.sceneRef.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (item.topCandidate?.name.toLowerCase().includes(searchQuery.toLowerCase()) ?? false) ||
        (item.topCandidate?.mmsi.includes(searchQuery) ?? false);

      const matchesStatus =
        statusFilter === "all" || item.status.toLowerCase() === statusFilter.toLowerCase();

      return matchesSearch && matchesStatus;
    });
  }, [cases, searchQuery, statusFilter]);

  // Sorting
  const sortedCases = React.useMemo(() => {
    const list = [...filteredCases];
    list.sort((a, b) => {
      let comp = 0;
      if (sortBy === "recency") {
        comp = new Date(b.detectionTime).getTime() - new Date(a.detectionTime).getTime();
      } else if (sortBy === "area") {
        comp = b.areaKm2 - a.areaKm2;
      } else if (sortBy === "score") {
        const scoreA = a.topCandidate?.score ?? 0;
        const scoreB = b.topCandidate?.score ?? 0;
        comp = scoreB - scoreA;
      }
      return sortOrder === "desc" ? comp : -comp;
    });
    return list;
  }, [filteredCases, sortBy, sortOrder]);

  const toggleSort = (field: "recency" | "area" | "score") => {
    if (sortBy === field) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(field);
      setSortOrder("desc");
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case "ready":
        return (
          <Badge variant="green" className="font-mono text-[10px] uppercase">
            Attribution Ready
          </Badge>
        );
      case "hindcasting":
        return (
          <Badge variant="blue" className="font-mono text-[10px] uppercase">
            Hindcast Active
          </Badge>
        );
      case "detecting":
        return (
          <Badge variant="orange" className="font-mono text-[10px] uppercase">
            SAR Ingestion
          </Badge>
        );
      default:
        return (
          <Badge variant="secondary" className="font-mono text-[10px] uppercase">
            {status}
          </Badge>
        );
    }
  };

  return (
    <div className={`space-y-4 ${className}`} data-testid="case-management-table">
      {/* Search & Filter Header Strip */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {/* Search Bar */}
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-on-dark-muted" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by case ID, region, vessel name, MMSI, or scene..."
            className="pl-9 text-xs"
          />
        </div>

        {/* Status Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-on-dark-muted font-medium mr-1 flex items-center gap-1">
            <Filter className="h-3 w-3" /> Status:
          </span>
          {[
            { id: "all", label: "All Cases" },
            { id: "ready", label: "Ready" },
            { id: "hindcasting", label: "Hindcasting" },
            { id: "detecting", label: "Detecting" },
          ].map((pill) => (
            <button
              key={pill.id}
              type="button"
              onClick={() => setStatusFilter(pill.id)}
              className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
                statusFilter === pill.id
                  ? "bg-brand-green text-brand-teal-deep shadow"
                  : "bg-brand-teal-deep border border-hairline-dark text-on-dark-muted hover:text-white"
              }`}
            >
              {pill.label}
            </button>
          ))}
        </div>
      </div>

      {/* Incident Case Table */}
      <div className="overflow-x-auto rounded-xl border border-hairline-dark bg-brand-teal-deep/90 shadow-xl backdrop-blur">
        <table className="w-full text-left text-xs">
          {/* Table Header */}
          <thead className="border-b border-hairline-dark bg-white/5 font-semibold text-on-dark-muted">
            <tr>
              <th className="py-3.5 pl-4 pr-3">Case Reference</th>
              <th className="px-3 py-3.5">SAR Chip</th>
              <th className="px-3 py-3.5">Surveillance Region</th>
              <th className="px-3 py-3.5">Sensor Instrument</th>
              <th className="px-3 py-3.5">
                <button
                  type="button"
                  onClick={() => toggleSort("recency")}
                  className="flex items-center gap-1 hover:text-white"
                >
                  <span>Acquisition Time</span>
                  <ArrowUpDown className="h-3 w-3" />
                </button>
              </th>
              <th className="px-3 py-3.5">
                <button
                  type="button"
                  onClick={() => toggleSort("area")}
                  className="flex items-center gap-1 hover:text-white"
                >
                  <span>Slick Footprint</span>
                  <ArrowUpDown className="h-3 w-3" />
                </button>
              </th>
              <th className="px-3 py-3.5">
                <button
                  type="button"
                  onClick={() => toggleSort("score")}
                  className="flex items-center gap-1 hover:text-white"
                >
                  <span>Top Candidate Suspect</span>
                  <ArrowUpDown className="h-3 w-3" />
                </button>
              </th>
              <th className="px-3 py-3.5">Status</th>
              <th className="py-3.5 pl-3 pr-4 text-right">Actions</th>
            </tr>
          </thead>

          {/* Table Body */}
          <tbody className="divide-y divide-hairline-dark text-on-dark-muted">
            {sortedCases.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-10 text-center text-sm text-on-dark-muted font-mono">
                  No incident cases match the selected filter criteria.
                </td>
              </tr>
            ) : (
              sortedCases.map((item) => {
                const formattedDate = item.detectionTime
                  .replace("T", " ")
                  .replace("Z", " UTC")
                  .substring(0, 19);

                return (
                  <tr
                    key={item.id}
                    className="transition-colors hover:bg-white/5 cursor-pointer"
                    onClick={() => onSelectCase?.(item)}
                  >
                    {/* Case Reference Code */}
                    <td className="py-3 pl-4 pr-3">
                      <div className="font-mono font-bold text-white text-xs">
                        {item.referenceCode}
                      </div>
                      <div className="font-mono text-[10px] text-on-dark-muted truncate max-w-[120px]">
                        {item.id}
                      </div>
                    </td>

                    {/* SAR Chip Preview Thumbnail */}
                    <td className="px-3 py-3">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedChipCase(item);
                        }}
                        className="group relative h-10 w-10 overflow-hidden rounded-md border border-hairline-dark bg-[#0a151e] p-0.5 hover:border-brand-green transition-colors"
                        title="Click to inspect calibrated SAR chip"
                      >
                        {/* Mini SVG Radar Thumbnail */}
                        <svg viewBox="0 0 256 256" className="w-full h-full">
                          <rect width="256" height="256" fill="#0d1c26" />
                          <path
                            d="M 64,88 Q 90,60 138,72 T 196,118 Q 204,164 162,188 T 92,176 Q 52,142 64,88 Z"
                            fill="#000e17"
                            stroke="#00ed64"
                            strokeWidth="8"
                          />
                        </svg>
                        <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Eye className="h-4 w-4 text-brand-green" />
                        </div>
                      </button>
                    </td>

                    {/* Surveillance Region */}
                    <td className="px-3 py-3">
                      <div className="font-medium text-white flex items-center gap-1.5">
                        <MapPin className="h-3.5 w-3.5 text-brand-green shrink-0" />
                        <span className="truncate max-w-[180px]">{item.regionName}</span>
                      </div>
                      <div className="font-mono text-[10px] text-on-dark-muted pl-5">
                        {item.coordinates[1].toFixed(2)}&deg; N, {item.coordinates[0].toFixed(2)}&deg; E
                      </div>
                    </td>

                    {/* Sensor Instrument */}
                    <td className="px-3 py-3">
                      <div className="font-medium text-white">{item.sensor}</div>
                      <div className="font-mono text-[10px] text-brand-green-soft truncate max-w-[150px]">
                        {item.sceneRef}
                      </div>
                    </td>

                    {/* Acquisition Time */}
                    <td className="px-3 py-3 font-mono text-xs">
                      <div className="text-white flex items-center gap-1">
                        <Clock className="h-3 w-3 text-on-dark-muted" />
                        <span>{formattedDate}</span>
                      </div>
                    </td>

                    {/* Slick Footprint */}
                    <td className="px-3 py-3 font-mono text-xs">
                      <div className="font-bold text-white">{item.areaKm2} km&sup2;</div>
                      {item.volumeM3 && (
                        <div className="text-[10px] text-on-dark-muted">~{item.volumeM3} m&sup3;</div>
                      )}
                    </td>

                    {/* Top Candidate Suspect (Rule 1 & Rule 6) */}
                    <td className="px-3 py-3">
                      {item.topCandidate ? (
                        <div className="space-y-0.5">
                          <div className="font-semibold text-white flex items-center gap-1.5">
                            <Anchor className="h-3 w-3 text-brand-green shrink-0" />
                            <span className="truncate max-w-[140px]">{item.topCandidate.name}</span>
                          </div>
                          <div className="flex items-center gap-2 font-mono text-[10px]">
                            <span className="text-brand-green font-bold">
                              S: {item.topCandidate.score.toFixed(3)}
                            </span>
                            <span className="text-hairline-dark">|</span>
                            <span className="text-on-dark-muted">
                              {item.topCandidate.confidencePct.toFixed(1)}% CI
                            </span>
                          </div>
                        </div>
                      ) : (
                        <span className="text-[11px] text-on-dark-muted italic">
                          Correlating tracks...
                        </span>
                      )}
                    </td>

                    {/* Status Badge */}
                    <td className="px-3 py-3">{getStatusBadge(item.status)}</td>

                    {/* Actions */}
                    <td className="py-3 pl-3 pr-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedChipCase(item);
                              }}
                              className="h-7 w-7 text-on-dark-muted hover:text-white"
                            >
                              <Radar className="h-3.5 w-3.5" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Inspect Calibrated SAR Chip</TooltipContent>
                        </Tooltip>

                        <Link href="/">
                          <Button
                            variant="secondary"
                            size="sm"
                            className="h-7 px-2.5 text-[11px] font-semibold gap-1"
                          >
                            <span>War Room</span>
                            <ChevronRight className="h-3 w-3" />
                          </Button>
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Satellite SAR Chip Preview Modal */}
      {selectedChipCase && (
        <SarChipModal
          isOpen={Boolean(selectedChipCase)}
          onClose={() => setSelectedChipCase(null)}
          caseId={selectedChipCase.referenceCode}
          sceneRef={selectedChipCase.sceneRef}
          regionName={selectedChipCase.regionName}
          sensor={selectedChipCase.sensor}
          detectionTime={selectedChipCase.detectionTime}
          slickAreaM2={selectedChipCase.areaKm2 * 1_000_000}
          confidencePct={selectedChipCase.topCandidate?.confidencePct ?? 92.4}
        />
      )}
    </div>
  );
}

export default CaseTable;
