"use client";

import * as React from "react";
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

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  TimeScrubber,
  type LiveVesselRanking,
  computeDynamicRankings,
} from "@/components/investigation";

export default function ForensicWarRoomPage() {
  const [driftFactor, setDriftFactor] = React.useState<number[]>([0.032]);

  // Investigation Replay & Temporal Scrubber State (TASK-043 / D4)
  const [simulationSeconds, setSimulationSeconds] = React.useState<number>(540); // default to midpoint CPA
  const [_simulationProgress, setSimulationProgress] = React.useState<number>(0.5);
  const [liveRankings, setLiveRankings] = React.useState<LiveVesselRanking[]>(() =>
    computeDynamicRankings(0.5)
  );

  return (
    <div className="flex min-h-screen flex-col bg-brand-teal-deep text-white">
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-40 border-b border-hairline-dark bg-brand-teal-deep/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-green text-brand-teal-deep shadow-md">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <span className="text-base font-bold tracking-tight text-white">
                AEGIS-Marine
              </span>
              <span className="ml-2 text-xs font-medium text-brand-green-soft">
                Forensic Operations v2.0
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Badge variant="greenSoft">
              <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-brand-green animate-pulse" />
              Surveillance Grid Active
            </Badge>
            <Button variant="default" size="sm">
              <Activity className="h-4 w-4" />
              New Incident
            </Button>
          </div>
        </div>
      </header>

      {/* Main War Room Canvas */}
      <main className="mx-auto flex-1 max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8">
        {/* Incident Context Banner */}
        <div className="rounded-xl border border-hairline-dark bg-brand-teal/40 p-6 backdrop-blur">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Badge variant="purple">SAR Sentinel-1A</Badge>
                <Badge variant="outline" className="font-mono text-xs">
                  CASE-2026-0814-IN-BOM
                </Badge>
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
                Offshore Mumbai High Corridor Incident
              </h1>
              <p className="font-mono text-xs text-on-dark-muted">
                Origin Coordinates: 18.9250° N, 72.8258° E | UTC Time: 2026-08-14T03:42:00Z
              </p>
            </div>

            <div className="flex items-center gap-3">
              <Dialog>
                <DialogTrigger asChild>
                  <Button variant="secondary" size="sm">
                    <FileText className="h-4 w-4" />
                    Forensic Dossier Summary
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Investigative Dossier Overview</DialogTitle>
                    <DialogDescription>
                      Cryptographic chain-of-custody and attribution summary for case CASE-2026-0814-IN-BOM.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 py-4 text-sm text-on-dark-muted">
                    <div className="rounded-md border border-hairline-dark bg-brand-teal-deep p-3 font-mono text-xs">
                      SHA-256 Digest: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
                    </div>
                    <p>
                      Attribution calculation combines backward Lagrangian particle dispersion with AIS track historical correlation.
                    </p>
                    <div className="flex items-center justify-between rounded-md border border-hairline-dark bg-brand-teal-deep p-3">
                      <span>Primary Attributed Candidate</span>
                      <Badge variant="orange">MMSI: 419001234</Badge>
                    </div>
                  </div>
                </DialogContent>
              </Dialog>

              <Button variant="default" size="sm">
                <Sliders className="h-4 w-4" />
                Simulate Scenario
              </Button>
            </div>
          </div>
        </div>

        {/* War Room Layout: Interactive Tabs & Primitives */}
        <Tabs defaultValue="map" className="w-full space-y-6">
          <TabsList className="border border-hairline-dark bg-brand-teal-deep/90">
            <TabsTrigger value="map" className="gap-2">
              <MapIcon className="h-4 w-4" />
              Geospatial Map Canvas
            </TabsTrigger>
            <TabsTrigger value="candidates" className="gap-2">
              <Anchor className="h-4 w-4" />
              Candidate Vessels
            </TabsTrigger>
            <TabsTrigger value="hindcast" className="gap-2">
              <Compass className="h-4 w-4" />
              Hindcast & Dispersion
            </TabsTrigger>
            <TabsTrigger value="layers" className="gap-2">
              <Layers className="h-4 w-4" />
              Sensor Layers
            </TabsTrigger>
          </TabsList>

          {/* Geospatial Map Canvas Tab */}
          <TabsContent value="map" className="space-y-4">
            <MarineMap
              initialCenter={[72.8258, 18.925]}
              initialZoom={8.5}
              boundingBox={[71.8, 18.2, 73.4, 19.8]}
              className="h-[620px] w-full shadow-2xl"
            >
              <DeckOverlay currentTime={simulationSeconds} />
            </MarineMap>

            {/* Interactive Investigation Replay Time-Scrubber (D4 / FR-17) */}
            <TimeScrubber
              totalDurationSeconds={1080}
              startTimestamp="2026-08-13T15:42:00Z"
              endTimestamp="2026-08-14T03:42:00Z"
              currentTimeSeconds={simulationSeconds}
              onTimeChange={(sec, prog) => {
                setSimulationSeconds(sec);
                setSimulationProgress(prog);
              }}
              onRankingsChange={(rankings) => {
                setLiveRankings(rankings);
              }}
            />
          </TabsContent>

          {/* Candidate Vessels Tab */}
          <TabsContent value="candidates" className="space-y-6">
            <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
              {/* Candidate 1 */}
              {(() => {
                const c1 = liveRankings.find((c) => c.mmsi === "419001234");
                const score = c1 ? c1.score : 0.884;
                const cpa = c1 ? c1.cpaDistanceNm : 0.42;
                const dt = c1 ? c1.temporalOffsetMin : -18;
                const rank = c1 ? c1.rank : 1;
                return (
                  <Card className="border-brand-green/40 hover:border-brand-green transition-colors">
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <Badge variant="green">Rank {rank}: Putative Culprit</Badge>
                        <span className="font-mono text-xs text-brand-green">
                          S_culprit: {score.toFixed(3)}
                        </span>
                      </div>
                      <CardTitle className="mt-2 text-xl font-bold">MT PACIFIC TRADER</CardTitle>
                      <CardDescription className="font-mono text-xs">
                        MMSI: 419001234 | IMO: 9283741
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      <div className="flex justify-between text-xs text-on-dark-muted">
                        <span>Spatial Closest Point (CPA):</span>
                        <span className="font-mono font-medium text-white">{cpa.toFixed(2)} NM</span>
                      </div>
                      <div className="flex justify-between text-xs text-on-dark-muted">
                        <span>Temporal Offset (Δt):</span>
                        <span className="font-mono font-medium text-white">
                          {dt >= 0 ? `+${dt}` : dt} min
                        </span>
                      </div>
                      <div className="flex justify-between text-xs text-on-dark-muted">
                        <span>Vessel Flag & Class:</span>
                        <span className="font-medium text-white">Panama | Crude Oil Tanker</span>
                      </div>
                      <div className="pt-2">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="secondary" size="sm" className="w-full">
                              Inspect Correlated Trajectory
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            View AIS track interpolated against release envelope
                          </TooltipContent>
                        </Tooltip>
                      </div>
                    </CardContent>
                  </Card>
                );
              })()}

              {/* Candidate 2 */}
              {(() => {
                const c2 = liveRankings.find((c) => c.mmsi === "563004567");
                const score = c2 ? c2.score : 0.541;
                const cpa = c2 ? c2.cpaDistanceNm : 2.15;
                const dt = c2 ? c2.temporalOffsetMin : 42;
                const rank = c2 ? c2.rank : 2;
                return (
                  <Card>
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <Badge variant="blue">Rank {rank}: Candidate</Badge>
                        <span className="font-mono text-xs text-on-dark-muted">
                          S_culprit: {score.toFixed(3)}
                        </span>
                      </div>
                      <CardTitle className="mt-2 text-xl font-bold">MV OCEAN STAR</CardTitle>
                      <CardDescription className="font-mono text-xs">
                        MMSI: 563004567 | IMO: 9451234
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      <div className="flex justify-between text-xs text-on-dark-muted">
                        <span>Spatial Closest Point (CPA):</span>
                        <span className="font-mono font-medium text-white">{cpa.toFixed(2)} NM</span>
                      </div>
                      <div className="flex justify-between text-xs text-on-dark-muted">
                        <span>Temporal Offset (Δt):</span>
                        <span className="font-mono font-medium text-white">
                          {dt >= 0 ? `+${dt}` : dt} min
                        </span>
                      </div>
                      <div className="flex justify-between text-xs text-on-dark-muted">
                        <span>Vessel Flag & Class:</span>
                        <span className="font-medium text-white">Singapore | Container Ship</span>
                      </div>
                      <div className="pt-2">
                        <Button variant="secondary" size="sm" className="w-full">
                          Inspect Correlated Trajectory
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                );
              })()}

              {/* Candidate 3 */}
              {(() => {
                const c3 = liveRankings.find((c) => c.mmsi === "412998877");
                const score = c3 ? c3.score : 0.219;
                const cpa = c3 ? c3.cpaDistanceNm : 4.8;
                const dt = c3 ? c3.temporalOffsetMin : 115;
                const rank = c3 ? c3.rank : 3;
                return (
                  <Card>
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <Badge variant="outline">Rank {rank}: Low Likelihood</Badge>
                        <span className="font-mono text-xs text-on-dark-muted">
                          S_culprit: {score.toFixed(3)}
                        </span>
                      </div>
                      <CardTitle className="mt-2 text-xl font-bold">SEABIRD EXPLORER</CardTitle>
                      <CardDescription className="font-mono text-xs">
                        MMSI: 412998877 | IMO: 9128833
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      <div className="flex justify-between text-xs text-on-dark-muted">
                        <span>Spatial Closest Point (CPA):</span>
                        <span className="font-mono font-medium text-white">{cpa.toFixed(2)} NM</span>
                      </div>
                      <div className="flex justify-between text-xs text-on-dark-muted">
                        <span>Temporal Offset (Δt):</span>
                        <span className="font-mono font-medium text-white">
                          {dt >= 0 ? `+${dt}` : dt} min
                        </span>
                      </div>
                      <div className="flex justify-between text-xs text-on-dark-muted">
                        <span>Vessel Flag & Class:</span>
                        <span className="font-medium text-white">India | Offshore Supply</span>
                      </div>
                      <div className="pt-2">
                        <Button variant="secondary" size="sm" className="w-full">
                          Inspect Correlated Trajectory
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                );
              })()}
            </div>
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
    </div>
  );
}
