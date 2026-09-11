"use client";

import * as React from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  Shield,
  Activity,
  Compass,
  FileText,
  Sliders,
  CheckCircle2,
  Layers,
  Radar,
  Anchor,
  Map as MapIcon,
  Scale,
  Network,
  Target,
  Ship,
  AlertTriangle,
  Play,
  Pause,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const MarineMap = dynamic(
  () => import("@/components/map").then((mod) => mod.MarineMap),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[550px] w-full items-center justify-center rounded-xl border border-hairline-dark bg-brand-teal-deep text-on-dark-muted font-mono text-sm animate-pulse">
        Initializing Dark Marine Cartography Canvas...
      </div>
    ),
  }
);

const DeckOverlay = dynamic(
  () => import("@/components/map").then((mod) => mod.DeckOverlay),
  { ssr: false }
);

import { DossierModal } from "@/components/dossier";
import {
  TimeScrubber,
  type LiveVesselRanking,
  computeDynamicRankings,
  WhatIfDrawer,
} from "@/components/investigation";
import {
  VesselRankingList,
  ExplainabilityDrawer,
  AlternativeExplanationsPanel,
  CounterfactualModal,
  EvidenceGraphView,
} from "@/components/attribution";
import type { VesselCandidate } from "@/types";

const INCIDENT_CENTER: [number, number] = [72.535, 18.87];
const INCIDENT_BOUNDS: [number, number, number, number] = [72.05, 18.65, 72.95, 19.05];

export default function ForensicWarRoomPage() {
  const [driftFactor, setDriftFactor] = React.useState<number[]>([0.032]);
  const [activeTab, setActiveTab] = React.useState<string>("map");
  const [selectedVesselMmsi, setSelectedVesselMmsi] = React.useState<number | null>(419001234);
  const [isExplainDrawerOpen, setIsExplainDrawerOpen] = React.useState<boolean>(false);
  const [explainingVessel, setExplainingVessel] = React.useState<VesselCandidate | null>(null);
  const [isCounterfactualModalOpen, setIsCounterfactualModalOpen] = React.useState<boolean>(false);
  const [counterfactualCandidate, setCounterfactualCandidate] = React.useState<VesselCandidate | null>(null);
  const [isWhatIfDrawerOpen, setIsWhatIfDrawerOpen] = React.useState<boolean>(false);
  const [isDossierModalOpen, setIsDossierModalOpen] = React.useState<boolean>(false);
  const [showForecast, setShowForecast] = React.useState<boolean>(true);

  // Investigation Replay & Temporal Scrubber State (TASK-043 / D4)
  const [simulationSeconds, setSimulationSeconds] = React.useState<number>(540); // default to midpoint CPA
  const [_simulationProgress, setSimulationProgress] = React.useState<number>(0.5);
  const [isPlaying, setIsPlaying] = React.useState<boolean>(false);
  const [_liveRankings, setLiveRankings] = React.useState<LiveVesselRanking[]>(() =>
    computeDynamicRankings(0.5)
  );

  // Memoized handlers to prevent render-storms and Maximum Update Depth errors
  const handleTimeChange = React.useCallback((sec: number, prog: number) => {
    setSimulationSeconds(sec);
    setSimulationProgress(prog);
  }, []);

  const handleRankingsChange = React.useCallback((rankings: LiveVesselRanking[]) => {
    setLiveRankings(rankings);
  }, []);

  const handlePlayStateChange = React.useCallback((playing: boolean) => {
    setIsPlaying(playing);
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-[#0B0F14] text-slate-100">
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-40 border-b border-[#1F2937] bg-[#0B0F14]/95 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-6 w-6 items-center justify-center rounded-sm bg-emerald-500/20 border border-emerald-500/40 text-emerald-400">
              <Shield className="h-4 w-4" />
            </div>
            <span className="text-xs font-mono font-semibold tracking-widest text-slate-300">
              AEGIS-MARINE // FORENSICS v2.0
            </span>
          </div>

          <div className="flex items-center gap-4">
            {/* Live Status Indicator */}
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              <span className="text-[11px] font-mono text-slate-400">
                GRID: ONLINE [SENTINEL-1A + AIS]
              </span>
            </div>

            <div className="flex items-center gap-2">
              <Link href="/cases">
                <Button
                  variant="secondary"
                  size="sm"
                  className="rounded-sm border border-slate-700 bg-slate-800/80 text-xs text-slate-200 hover:border-slate-500 gap-1.5 px-3 py-1.5 h-7"
                >
                  <Radar className="h-3.5 w-3.5 text-emerald-400" />
                  <span>Incident Cases</span>
                </Button>
              </Link>
              <Link href="/cases">
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 text-xs px-3 py-1.5 rounded-sm font-mono font-medium transition-colors"
                >
                  <Activity className="h-3.5 w-3.5" />
                  <span>New Incident</span>
                </button>
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Main War Room Canvas */}
      <main className="mx-auto flex-1 max-w-7xl px-4 py-6 sm:px-6 lg:px-8 space-y-6">
        {/* Incident Context Banner */}
        <div className="rounded-sm border border-[#1F2937] bg-[#111720] p-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-2">
              <h1 className="text-xl font-bold tracking-tight text-white sm:text-2xl font-sans">
                Offshore Mumbai High Corridor Incident
              </h1>
              {/* Structured Telemetry Header Strip */}
              <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-mono">
                <span className="bg-slate-900/80 border border-slate-800 px-2 py-0.5 text-slate-300 rounded-sm">
                  INCIDENT ID: BOM-2026-0814
                </span>
                <span className="text-slate-600 select-none">│</span>
                <span className="bg-slate-900/80 border border-slate-800 px-2 py-0.5 text-slate-300 rounded-sm">
                  ORIGIN: 18.9250°N, 72.8258°E
                </span>
                <span className="text-slate-600 select-none">│</span>
                <span className="bg-slate-900/80 border border-slate-800 px-2 py-0.5 text-slate-300 rounded-sm">
                  UTC: 2026-08-14 03:42:00Z
                </span>
                <span className="text-slate-600 select-none">│</span>
                <span className="bg-slate-900/80 border border-slate-800 px-2 py-0.5 text-emerald-400 rounded-sm">
                  SOURCE: SAR SENTINEL-1A
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsDossierModalOpen(true)}
                className="rounded-sm border border-slate-700 bg-slate-800/80 text-xs text-slate-200 hover:border-slate-500 gap-1.5 h-8 px-3"
              >
                <FileText className="h-3.5 w-3.5" />
                <span>Forensic Dossier Summary</span>
              </Button>

              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsWhatIfDrawerOpen(true)}
                className="rounded-sm border border-slate-700 bg-slate-800/80 text-xs text-slate-200 hover:border-slate-500 gap-1.5 h-8 px-3"
              >
                <Sliders className="h-3.5 w-3.5" />
                <span>Simulate Scenario</span>
              </Button>
            </div>
          </div>
        </div>

        {/* War Room Layout: Interactive Tabs & Primitives */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full space-y-4">
          <TabsList className="border-b border-[#1F2937] bg-[#0B0F14]">
            <TabsTrigger value="map" className="gap-2">
              <MapIcon className="h-3.5 w-3.5" />
              Geospatial Map Canvas
            </TabsTrigger>
            <TabsTrigger value="candidates" className="gap-2">
              <Anchor className="h-3.5 w-3.5" />
              Candidate Vessels
            </TabsTrigger>
            <TabsTrigger value="alternatives" className="gap-2">
              <Scale className="h-3.5 w-3.5" />
              Alternative Hypotheses (Rule 5)
            </TabsTrigger>
            <TabsTrigger value="graph" className="gap-2">
              <Network className="h-3.5 w-3.5" />
              Evidence Graph (DAG)
            </TabsTrigger>
            <TabsTrigger value="hindcast" className="gap-2">
              <Compass className="h-3.5 w-3.5" />
              Hindcast & Dispersion
            </TabsTrigger>
            <TabsTrigger value="layers" className="gap-2">
              <Layers className="h-3.5 w-3.5" />
              Sensor Layers
            </TabsTrigger>
          </TabsList>

          {/* Geospatial Map Canvas Tab */}
          <TabsContent value="map" className="space-y-4">
            {/* Live Interconnected Phase Pipeline / Stepper */}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-sm border border-[#1F2937] bg-[#111720] px-4 py-2.5">
              <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
                {/* [ ▶ REPLAY ] button */}
                <button
                  type="button"
                  onClick={() => setIsPlaying((prev) => !prev)}
                  className={`inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1 transition-all ${
                    isPlaying
                      ? "border-emerald-400/60 bg-emerald-500/20 text-emerald-300"
                      : "border-slate-700 bg-slate-900/60 text-slate-300 hover:border-slate-500 hover:text-white"
                  }`}
                >
                  {isPlaying ? (
                    <>
                      <span className="relative flex h-1.5 w-1.5">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      </span>
                      <Pause className="h-3 w-3" />
                      <span>[ ⏸ PAUSE ]</span>
                    </>
                  ) : (
                    <>
                      <Play className="h-3 w-3 fill-current" />
                      <span>[ ▶ REPLAY ]</span>
                    </>
                  )}
                </button>

                <span className="text-slate-700 select-none">│</span>

                {/* (01) 15:42 SPILL ORIGIN */}
                <button
                  type="button"
                  onClick={() => {
                    setIsPlaying(false);
                    setSimulationSeconds(0);
                    setSimulationProgress(0);
                  }}
                  className={`inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1 transition-all ${
                    simulationSeconds === 0 && !isPlaying
                      ? "border-amber-400/60 bg-amber-500/15 text-amber-300"
                      : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-800"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      simulationSeconds === 0 && !isPlaying ? "bg-amber-400" : "bg-slate-600"
                    }`}
                  />
                  <span>(01) 15:42 SPILL ORIGIN</span>
                </button>

                <span className="text-slate-700 select-none">───</span>

                {/* (02) 21:42 SUSPECT CPA */}
                <button
                  type="button"
                  onClick={() => {
                    setIsPlaying(false);
                    setSimulationSeconds(540);
                    setSimulationProgress(0.5);
                  }}
                  className={`inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1 transition-all ${
                    Math.abs(simulationSeconds - 540) < 30 && !isPlaying
                      ? "border-sky-400/60 bg-sky-500/15 text-sky-300"
                      : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-800"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      Math.abs(simulationSeconds - 540) < 30 && !isPlaying ? "bg-sky-400" : "bg-slate-600"
                    }`}
                  />
                  <span>(02) 21:42 SUSPECT CPA</span>
                </button>

                <span className="text-slate-700 select-none">───</span>

                {/* (03) 03:42 SAR DETECT */}
                <button
                  type="button"
                  onClick={() => {
                    setIsPlaying(false);
                    setSimulationSeconds(1080);
                    setSimulationProgress(1.0);
                  }}
                  className={`inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1 transition-all ${
                    simulationSeconds === 1080 && !isPlaying
                      ? "border-emerald-400/60 bg-emerald-500/15 text-emerald-300"
                      : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-800"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      simulationSeconds === 1080 && !isPlaying ? "bg-emerald-400" : "bg-slate-600"
                    }`}
                  />
                  <span>(03) 03:42 SAR DETECT</span>
                </button>

                <span className="text-slate-700 select-none">───</span>

                {/* [ ⚠ +24H FORECAST ] */}
                <button
                  type="button"
                  onClick={() => setShowForecast((prev) => !prev)}
                  className={`inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1 transition-all ${
                    showForecast
                      ? "border-amber-500/60 bg-amber-500/15 text-amber-300"
                      : "border-slate-800 bg-slate-900/40 text-slate-500 hover:text-slate-300"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      showForecast ? "bg-amber-400" : "bg-slate-600"
                    }`}
                  />
                  <span>[ ⚠ +24H FORECAST ]</span>
                </button>
              </div>
            </div>

            <MarineMap
              initialCenter={INCIDENT_CENTER}
              initialZoom={9.2}
              boundingBox={INCIDENT_BOUNDS}
              className="h-[620px] w-full shadow-2xl"
            >
              <DeckOverlay
                currentTime={simulationSeconds}
                showForecast={showForecast}
                showLabels={true}
              />
            </MarineMap>

            {/* Interactive Investigation Replay Time-Scrubber (D4 / FR-17) */}
            <TimeScrubber
              totalDurationSeconds={1080}
              startTimestamp="2026-08-13T15:42:00Z"
              endTimestamp="2026-08-14T03:42:00Z"
              currentTimeSeconds={simulationSeconds}
              isPlaying={isPlaying}
              onPlayStateChange={handlePlayStateChange}
              onTimeChange={handleTimeChange}
              onRankingsChange={handleRankingsChange}
            />
          </TabsContent>

          {/* Candidate Vessels Tab (TASK-045 / Rules 1, 3, 4, 6) */}
          <TabsContent value="candidates" className="space-y-6">
            {/* Rule 5 Multi-Hypothesis Quick Switch Banner */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-hairline-dark bg-brand-teal/20 p-4">
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <Badge variant="purple" className="text-[10px]">Product Rule 5</Badge>
                  <span className="text-xs font-semibold text-white">
                    3 Non-Vessel Alternative Hypotheses Evaluated
                  </span>
                </div>
                <p className="text-[11px] text-on-dark-muted">
                  Natural Seep (12.5%), SAR Lookalike (6.0%), Unregistered/Dark Target (40.0%).
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setActiveTab("graph")}
                  className="gap-1.5 text-xs text-sky-400 hover:text-white shrink-0"
                >
                  <Network className="h-3.5 w-3.5" />
                  <span>Evidence Graph (DAG)</span>
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setActiveTab("alternatives")}
                  className="gap-1.5 text-xs text-brand-green hover:text-white shrink-0"
                >
                  <Scale className="h-3.5 w-3.5" />
                  <span>Compare Alternative Explanations</span>
                </Button>
              </div>
            </div>

            <VesselRankingList
              selectedMmsi={selectedVesselMmsi}
              onSelectCandidate={(cand) => setSelectedVesselMmsi(cand.mmsi)}
              onInspectTrack={(cand) => {
                setSelectedVesselMmsi(cand.mmsi);
                setActiveTab("map");
              }}
              onOpenExplainability={(cand) => {
                setExplainingVessel(cand);
                setIsExplainDrawerOpen(true);
              }}
            />
          </TabsContent>

          {/* Alternative Hypotheses & Lookalikes Tab (TASK-047 / Rule 5, Feature 7) */}
          <TabsContent value="alternatives" className="space-y-6">
            <AlternativeExplanationsPanel
              caseId="case-2026-0814-in-bom"
              topCandidateScore={88.4}
              topCandidateName="MT PACIFIC TRADER"
            />
          </TabsContent>

          {/* Causal Evidence Graph Tab (TASK-049 / Feature 11 / P5) */}
          <TabsContent value="graph" className="space-y-6">
            <EvidenceGraphView
              caseId="case-2026-0814-in-bom"
              selectedMmsi={selectedVesselMmsi}
              onFocusCoordinate={(_coords) => {
                setActiveTab("map");
              }}
            />
          </TabsContent>

          {/* Hindcast & Dispersion Tab */}
          <TabsContent value="hindcast" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Radar className="h-5 w-5 text-brand-green" />
                  What-If Trajectory Parameter Overrides
                </CardTitle>
                <CardDescription>
                  Tune physics model parameters and re-execute hindcasting without re-running SAR segmentation.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="font-medium">Wind Drift Factor (c_w):</span>
                    <span className="font-mono text-brand-green font-semibold">
                      {driftFactor[0].toFixed(3)}
                    </span>
                  </div>
                  <Slider
                    min={0.015}
                    max={0.05}
                    step={0.001}
                    value={driftFactor}
                    onValueChange={setDriftFactor}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-on-dark-muted">
                    <span>Light Sheen (0.015)</span>
                    <span>Standard Heavy Crude (0.030)</span>
                    <span>Heavy Windage (0.050)</span>
                  </div>
                </div>

                <div className="flex items-center justify-between rounded-lg border border-hairline-dark bg-brand-teal-deep p-4">
                  <div className="space-y-1">
                    <div className="text-sm font-medium">Attribution Uncertainty Covariance</div>
                    <div className="font-mono text-xs text-on-dark-muted">
                      Semi-major axis: 2.45 NM | Semi-minor axis: 0.82 NM
                    </div>
                  </div>
                  <Badge variant="orange">Confidence: 89.2%</Badge>
                </div>

                <Button
                  variant="default"
                  size="sm"
                  onClick={() => setIsWhatIfDrawerOpen(true)}
                  className="w-full gap-2 text-xs font-semibold bg-brand-green text-brand-teal-deep hover:bg-brand-green/90"
                >
                  <Sliders className="h-4 w-4" />
                  <span>Launch What-If Scenario Exploration Engine</span>
                </Button>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Sensor Layers Tab */}
          <TabsContent value="layers" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Layers className="h-5 w-5 text-brand-green" />
                  Active Geospatial Layers
                </CardTitle>
                <CardDescription>
                  Configured cartographic overlays adhering to dark marine canvas specification.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="flex items-center justify-between rounded-lg border border-hairline-dark p-4">
                  <div>
                    <div className="text-sm font-semibold">Sentinel-1A SAR VV/VH</div>
                    <div className="text-xs text-on-dark-muted">Copernicus Hub GRDH scene</div>
                  </div>
                  <CheckCircle2 className="h-5 w-5 text-brand-green" />
                </div>
                <div className="flex items-center justify-between rounded-lg border border-hairline-dark p-4">
                  <div>
                    <div className="text-sm font-semibold">HYCOM Surface Ocean Currents</div>
                    <div className="text-xs text-on-dark-muted">3-hour interval vector grid</div>
                  </div>
                  <CheckCircle2 className="h-5 w-5 text-brand-green" />
                </div>
                <div className="flex items-center justify-between rounded-lg border border-hairline-dark p-4">
                  <div>
                    <div className="text-sm font-semibold">ERA5 10m Wind Fields</div>
                    <div className="text-xs text-on-dark-muted">ECMWF reanalysis atmospheric forcing</div>
                  </div>
                  <CheckCircle2 className="h-5 w-5 text-brand-green" />
                </div>
                <div className="flex items-center justify-between rounded-lg border border-hairline-dark p-4">
                  <div>
                    <div className="text-sm font-semibold">Terrestrial & Satellite AIS</div>
                    <div className="text-xs text-on-dark-muted">Spire / exactEarth feed stream</div>
                  </div>
                  <CheckCircle2 className="h-5 w-5 text-brand-green" />
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>

      {/* Footer */}
      <footer className="border-t border-hairline-dark bg-brand-teal-deep py-6 text-center text-xs text-on-dark-muted">
        <p>
          AEGIS-Marine Maritime Forensic Intelligence Platform &copy; 2026. Strictly adhering to Rule 6 terminology standards.
        </p>
      </footer>

      {/* Forensic Explainability Drawer (TASK-046 / Feature 1 / Rule 2) */}
      <ExplainabilityDrawer
        open={isExplainDrawerOpen}
        onOpenChange={setIsExplainDrawerOpen}
        candidate={explainingVessel}
        caseId="case-2026-0814-in-bom"
        onInspectTrack={(cand) => {
          setSelectedVesselMmsi(cand.mmsi);
          setActiveTab("map");
        }}
        onOpenCounterfactual={(cand) => {
          setCounterfactualCandidate(cand);
          setIsCounterfactualModalOpen(true);
        }}
      />

      {/* Interactive Counterfactual Comparison View (TASK-048 / Feature 2 / D2) */}
      <CounterfactualModal
        open={isCounterfactualModalOpen}
        onOpenChange={setIsCounterfactualModalOpen}
        candidate={counterfactualCandidate}
        caseId="case-2026-0814-in-bom"
      />

      {/* "What-If" Scenario Control Drawer (TASK-050 / Feature 3 / P3) */}
      <WhatIfDrawer
        open={isWhatIfDrawerOpen}
        onOpenChange={setIsWhatIfDrawerOpen}
        caseId="case-2026-0814-in-bom"
        onApplyScenario={(scenario) => {
          if (scenario.comparison.rank_shifts && scenario.comparison.rank_shifts.length > 0) {
            setSelectedVesselMmsi(scenario.comparison.rank_shifts[0].mmsi);
          }
          if (scenario.applied_parameters.wind_drift_factor) {
            setDriftFactor([scenario.applied_parameters.wind_drift_factor]);
          }
          setIsWhatIfDrawerOpen(false);
          setActiveTab("candidates");
        }}
      />

      {/* Legal Evidence Dossier & PDF Export Modal (TASK-051 / FR-20 / C13) */}
      <DossierModal
        open={isDossierModalOpen}
        onOpenChange={setIsDossierModalOpen}
        caseId="case-2026-0814-in-bom"
      />
    </div>
  );
}
