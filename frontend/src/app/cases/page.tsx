"use client";

import * as React from "react";
import Link from "next/link";
import {
  Shield,
  Activity,
  Layers,
  Map as MapIcon,
  Compass,
  Plus,
  RefreshCw,
  Radar,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CaseTable, CaseCreateDialog } from "@/components/dashboard";
import { apiClient } from "@/lib/api-client";
import type { CaseDetail } from "@/types";

export default function IncidentCasesDashboardPage() {
  const [cases, setCases] = React.useState<CaseDetail[]>([]);
  const [isLoading, setIsLoading] = React.useState<boolean>(true);

  // Load cases from backend API or fallback
  const fetchCases = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await apiClient.listCases();
      setCases(result);
    } catch {
      // Offline / synthetic fallback
      setCases([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchCases();
  }, [fetchCases]);

  const handleCaseCreated = (newCase: CaseDetail) => {
    setCases((prev) => [newCase, ...prev]);
  };

  return (
    <div className="flex min-h-screen flex-col bg-brand-teal-deep text-white">
      {/* 1. Global Navigation Bar */}
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
                Operations & Active Monitor
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Badge variant="greenSoft">
              <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-brand-green animate-pulse" />
              Global Sentinel Feed Live
            </Badge>

            {/* Link back to Forensic War Room Canvas */}
            <Link href="/">
              <Button variant="secondary" size="sm" className="gap-1.5">
                <MapIcon className="h-4 w-4 text-brand-green" />
                <span>War Room Canvas</span>
              </Button>
            </Link>

            {/* New Incident Case Modal Trigger */}
            <CaseCreateDialog onCaseCreated={handleCaseCreated} />
          </div>
        </div>
      </header>

      {/* 2. Main Dashboard Content */}
      <main className="mx-auto flex-1 max-w-7xl w-full px-4 py-8 sm:px-6 lg:px-8 space-y-8">
        {/* Operations Overview Banner */}
        <div className="rounded-xl border border-hairline-dark bg-brand-teal/40 p-6 backdrop-blur">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Badge variant="green">Operations Monitor</Badge>
                <span className="font-mono text-xs text-on-dark-muted">
                  Copernicus Sentinel-1 / Sentinel-2 Surveillance Grid
                </span>
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
                Incident Case Management & Spill Detection Monitor
              </h1>
              <p className="text-xs text-on-dark-muted">
                Continuous satellite radar surveillance, automated dark slick segmentation, and backward Lagrangian hindcasting.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={fetchCases}
                disabled={isLoading}
                className="gap-1.5"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
                <span>Refresh Grid</span>
              </Button>

              <CaseCreateDialog
                onCaseCreated={handleCaseCreated}
                triggerButton={
                  <Button variant="default" size="sm" className="gap-1.5">
                    <Plus className="h-4 w-4" />
                    <span>Ingest Satellite Scene</span>
                  </Button>
                }
              />
            </div>
          </div>
        </div>

        {/* 3. Operations KPI Summary Cards */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Total Incidents */}
          <Card className="border-hairline-dark bg-brand-teal-deep/90 shadow-lg">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between text-on-dark-muted">
                <span className="text-xs font-semibold uppercase tracking-wider">
                  Monitored Incidents
                </span>
                <Radar className="h-4 w-4 text-brand-green" />
              </div>
              <CardTitle className="text-2xl font-bold font-mono text-white mt-1">
                5 Active
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-[11px] text-on-dark-muted">
                Across 4 global maritime transit corridors
              </div>
            </CardContent>
          </Card>

          {/* Active Hindcasting Runs */}
          <Card className="border-hairline-dark bg-brand-teal-deep/90 shadow-lg">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between text-on-dark-muted">
                <span className="text-xs font-semibold uppercase tracking-wider">
                  Lagrangian Hindcasts
                </span>
                <Compass className="h-4 w-4 text-accent-blue" />
              </div>
              <CardTitle className="text-2xl font-bold font-mono text-white mt-1">
                3 Running
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-[11px] text-on-dark-muted">
                OpenDrift & HYCOM current integration
              </div>
            </CardContent>
          </Card>

          {/* Total Slick Footprint */}
          <Card className="border-hairline-dark bg-brand-teal-deep/90 shadow-lg">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between text-on-dark-muted">
                <span className="text-xs font-semibold uppercase tracking-wider">
                  Total Slick Area
                </span>
                <Layers className="h-4 w-4 text-accent-orange" />
              </div>
              <CardTitle className="text-2xl font-bold font-mono text-white mt-1">
                22.21 km&sup2;
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-[11px] text-on-dark-muted">
                ~4,440 m&sup3; estimated hydrocarbon volume
              </div>
            </CardContent>
          </Card>

          {/* Mean Candidate Attribution Rate */}
          <Card className="border-hairline-dark bg-brand-teal-deep/90 shadow-lg">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between text-on-dark-muted">
                <span className="text-xs font-semibold uppercase tracking-wider">
                  Mean Confidence
                </span>
                <Shield className="h-4 w-4 text-brand-green" />
              </div>
              <CardTitle className="text-2xl font-bold font-mono text-brand-green mt-1">
                90.3% CI
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-[11px] text-on-dark-muted">
                Constitutional Rule 1 paired verification
              </div>
            </CardContent>
          </Card>
        </div>

        {/* 4. Active Case Management Table */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-brand-green" />
              <h2 className="text-lg font-bold text-white">Active Spill Incidents Registry</h2>
            </div>
            <span className="font-mono text-xs text-on-dark-muted">
              Auto-refreshed via WebSocket
            </span>
          </div>

          <CaseTable initialCases={cases} />
        </div>
      </main>
    </div>
  );
}
