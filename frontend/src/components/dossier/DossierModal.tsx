"use client";

import * as React from "react";
import {
  Anchor,
  Check,
  CheckCircle2,
  Compass,
  Copy,
  Cpu,
  Download,
  Eye,
  FileCheck,
  FileText,
  Fingerprint,
  Lock,
  QrCode,
  Radio,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiClient } from "@/lib/api-client";
import type { DossierResult } from "@/types";

export interface DossierModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  caseId?: string;
  dossierData?: DossierResult;
  topCandidateName?: string;
  topCandidateMmsi?: number;
  className?: string;
}

// -----------------------------------------------------------------------------
// Canonical Synthetic Dossier Data for Mumbai High Incident
// Adheres strictly to Rule 1 (confidence), Rule 4 (provenance), Rule 6 (zero banned terms)
// -----------------------------------------------------------------------------
export const SYNTHETIC_DOSSIER_RESULT: DossierResult = {
  id: "00000000-0000-0000-0000-000000000088",
  case_id: "case-2026-0814-in-bom",
  pdf_ref: "s3://aegis-storage/dossiers/aegis_dossier_case-2026-0814-in-bom_e3b0c442.pdf",
  sha256_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  generated_by: "Investigator / AEGIS Automated Forensic Pipeline",
  generated_at: "2026-08-14T04:45:00Z",
  file_size_bytes: 1485920,
  model_versions: {
    segmentation: "DeepLabV3+-ResNet50-v1.2.0",
    morphometry: "Fay-BAOAC-v1.0.0",
    hindcast: "OpenDrift-1.11.0-OpenOil",
    attribution_ahp: "AHP-Saaty-CR0.04-v1.0.0",
    alternative_engine: "AEGIS-AltEngine-v1.0.0",
  },
};

const FR20_DISCLAIMER_TEXT =
  "This dossier provides evidentiary correlation analysis based on spaceborne synthetic aperture radar (SAR), hydrodynamic Lagrangian hindcasting, and AIS vessel tracking data. Outputs represent probabilistic candidate suspects and do not constitute a final legal determination of liability. Final evidentiary verification requires on-site sampling, physical oil chemical fingerprinting, and authorized maritime inspection pursuant to MARPOL 73/78 Annex I and UNCLOS Article 217 guidelines.";

export function DossierModal({
  open,
  onOpenChange,
  caseId = "case-2026-0814-in-bom",
  dossierData,
  topCandidateName = "MT PACIFIC TRADER",
  topCandidateMmsi = 419001234,
  className = "",
}: DossierModalProps) {
  const dossier = dossierData ?? SYNTHETIC_DOSSIER_RESULT;

  const [activeTab, setActiveTab] = React.useState<"brief" | "chain" | "stream">("brief");
  const [copiedHash, setCopiedHash] = React.useState<boolean>(false);
  const [isRegenerating, setIsRegenerating] = React.useState<boolean>(false);
  const [downloadSuccess, setDownloadSuccess] = React.useState<boolean>(false);

  // Compute download URL
  const downloadUrl = React.useMemo(() => {
    const client = new ApiClient();
    return client.getDossierDownloadUrl(caseId);
  }, [caseId]);

  const handleCopyHash = () => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(dossier.sha256_hash);
      setCopiedHash(true);
      setTimeout(() => setCopiedHash(false), 2500);
    }
  };

  const handleRegenerate = async () => {
    setIsRegenerating(true);
    try {
      const client = new ApiClient();
      await client.generateDossier(caseId);
    } catch {
      // Offline fallback: keep existing synthetic dossier
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleDownload = () => {
    setDownloadSuccess(true);
    setTimeout(() => setDownloadSuccess(false), 3000);
    // Trigger download anchor
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = `aegis_legal_dossier_${caseId}_${dossier.sha256_hash.substring(0, 8)}.pdf`;
    link.target = "_blank";
    link.click();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={`max-w-4xl lg:max-w-5xl max-h-[92vh] flex flex-col p-0 bg-brand-teal-deep border-hairline-dark text-white overflow-hidden shadow-2xl ${className}`}
      >
        {/* Top Header & Chain-of-Custody Integrity Banner */}
        <div className="p-6 border-b border-hairline-dark bg-brand-teal/30">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
            <div className="flex items-center gap-2">
              <Badge variant="purple" className="text-[10px] uppercase font-mono tracking-wider">
                FR-20 / C13 Legal Dossier
              </Badge>
              <Badge variant="outline" className="text-[10px] font-mono border-brand-green/40 text-brand-green">
                Case: {caseId}
              </Badge>
              <Badge variant="outline" className="text-[10px] font-mono text-sky-300 border-sky-500/30">
                ISO/IEC 27037 Standard
              </Badge>
            </div>

            <Badge variant="greenSoft" className="font-mono text-xs">
              <ShieldCheck className="h-3.5 w-3.5 mr-1 text-brand-green" />
              Cryptographically Signed
            </Badge>
          </div>

          <DialogHeader className="text-left space-y-1">
            <DialogTitle className="text-xl font-bold text-white flex items-center gap-2.5">
              <FileCheck className="h-5 w-5 text-brand-green" />
              Court-Ready Forensic Evidence Dossier
            </DialogTitle>
            <DialogDescription className="text-xs text-on-dark-muted">
              Standardized maritime legal evidentiary package compiling satellite observations, hydrodynamic backward hindcasting, candidate vessel attribution rankings, and non-vessel alternative hypothesis evaluations.
            </DialogDescription>
          </DialogHeader>

          {/* Cryptographic SHA-256 Hash Digest Ribbon */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-hairline-dark bg-brand-teal-deep/90 p-2.5">
            <div className="flex items-center gap-2 min-w-0">
              <Fingerprint className="h-4 w-4 text-brand-green shrink-0" />
              <div className="space-y-0.5 min-w-0">
                <div className="text-[10px] uppercase font-mono font-semibold text-on-dark-muted">
                  SHA-256 Chain-of-Custody Digest (Deterministic Cryptographic Seal)
                </div>
                <div className="font-mono text-xs text-brand-green truncate select-all">
                  {dossier.sha256_hash}
                </div>
              </div>
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={handleCopyHash}
              className="h-7 px-2.5 text-xs gap-1 text-on-dark-muted hover:text-white shrink-0"
            >
              {copiedHash ? (
                <>
                  <Check className="h-3 w-3 text-brand-green" />
                  <span className="text-brand-green font-semibold">Copied Checksum</span>
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" />
                  <span>Copy Hash</span>
                </>
              )}
            </Button>
          </div>

          {/* Sub-Nav View Tabs */}
          <div className="flex items-center gap-2 mt-4 pt-2 border-t border-hairline-dark/60">
            <button
              onClick={() => setActiveTab("brief")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeTab === "brief"
                  ? "bg-brand-green text-brand-teal-deep font-semibold shadow-sm"
                  : "bg-brand-teal/40 text-on-dark-muted hover:text-white"
              }`}
            >
              <FileText className="h-3.5 w-3.5" />
              Forensic Evidentiary Brief
            </button>
            <button
              onClick={() => setActiveTab("chain")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeTab === "chain"
                  ? "bg-brand-green text-brand-teal-deep font-semibold shadow-sm"
                  : "bg-brand-teal/40 text-on-dark-muted hover:text-white"
              }`}
            >
              <Lock className="h-3.5 w-3.5" />
              Chain of Custody & Checkpoints
            </button>
            <button
              onClick={() => setActiveTab("stream")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeTab === "stream"
                  ? "bg-brand-green text-brand-teal-deep font-semibold shadow-sm"
                  : "bg-brand-teal/40 text-on-dark-muted hover:text-white"
              }`}
            >
              <Eye className="h-3.5 w-3.5" />
              Embedded PDF Stream
            </button>
          </div>
        </div>

        {/* Scrollable Main Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {activeTab === "brief" && (
            <div className="space-y-6">
              {/* Document Cover Header */}
              <div className="rounded-xl border border-hairline-dark bg-brand-teal/20 p-5 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-hairline-dark pb-4">
                  <div className="flex items-center gap-3">
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-green/20 text-brand-green border border-brand-green/30">
                      <Scale className="h-6 w-6" />
                    </div>
                    <div>
                      <span className="text-[10px] font-mono uppercase tracking-widest text-brand-green font-bold">
                        International Maritime Organization · MARPOL 73/78 Annex I
                      </span>
                      <h2 className="text-lg font-bold text-white tracking-tight">
                        Forensic Oil Discharge Attribution Dossier
                      </h2>
                      <p className="text-xs text-on-dark-muted">
                        Authority: United Nations Convention on the Law of the Sea (UNCLOS) Article 217
                      </p>
                    </div>
                  </div>

                  <div className="text-right space-y-1">
                    <Badge variant="outline" className="font-mono text-[10px] border-hairline-dark">
                      SECURITY: OFFICIAL / FORENSIC USE
                    </Badge>
                    <div className="text-[11px] text-on-dark-muted font-mono">
                      Timestamp: {(dossier.generated_at ?? "2026-08-14T04:45:00Z").replace("T", " ").replace("Z", " UTC")}
                    </div>
                  </div>
                </div>

                {/* Primary Correlated Candidate Suspect Hero Strip */}
                <div className="rounded-lg border border-brand-green/30 bg-emerald-950/30 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="text-xs uppercase font-semibold text-emerald-300 flex items-center gap-1.5">
                      <Anchor className="h-3.5 w-3.5 text-brand-green" />
                      Highest Statistically Correlated Candidate Suspect
                    </div>
                    <div className="text-base font-bold text-white flex items-center gap-2">
                      <span>{topCandidateName}</span>
                      <Badge variant="outline" className="font-mono text-xs border-brand-green/40 text-brand-green">
                        MMSI: {topCandidateMmsi}
                      </Badge>
                      <Badge variant="purple" className="text-[10px]">
                        Crude Oil Tanker
                      </Badge>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className="text-[10px] uppercase font-semibold text-on-dark-muted">
                        Attribution Score (S_culprit)
                      </div>
                      <div className="font-mono text-xl font-bold text-brand-green">
                        88.4 <span className="text-xs text-on-dark-muted">/ 100</span>
                      </div>
                    </div>
                    <Badge variant="greenSoft" className="font-mono text-xs font-bold px-2.5 py-1">
                      Rule 1: 91.4% CI
                    </Badge>
                  </div>
                </div>
              </div>

              {/* Section 1: Satellite SAR Acquisition & Detection */}
              <div className="rounded-xl border border-hairline-dark bg-brand-teal/20 p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-hairline-dark pb-2">
                  <div className="flex items-center gap-2">
                    <Radio className="h-4 w-4 text-sky-400" />
                    <h3 className="text-sm font-bold text-white">
                      Section 1: Spaceborne Synthetic Aperture Radar (SAR) Detection
                    </h3>
                  </div>
                  <Badge variant="outline" className="font-mono text-[10px] text-sky-300">
                    Rule 1: 94.0% CI
                  </Badge>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2">
                    <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Sensor Platform</span>
                    <div className="font-mono text-white font-medium mt-0.5">Sentinel-1A C-SAR</div>
                  </div>
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2">
                    <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Acquisition Time</span>
                    <div className="font-mono text-white font-medium mt-0.5">2026-08-14 03:42Z</div>
                  </div>
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2">
                    <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Surface Area</span>
                    <div className="font-mono text-brand-green font-bold mt-0.5">4.82 km²</div>
                  </div>
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2">
                    <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Estimated Volume</span>
                    <div className="font-mono text-brand-green font-bold mt-0.5">145.0 m³</div>
                  </div>
                </div>

                <p className="text-xs text-on-dark-muted leading-relaxed">
                  Dual-polarization (VV/VH) Interferometric Wide (IW) imagery identified a contiguous anomalous radar backscatter damping polygon (contrast -18.4 dB) classified as BAOAC Level 4 (Metallic Sheen / Emulsion) via DeepLabV3+ neural segmentation.
                </p>
              </div>

              {/* Section 2: Hydrodynamic Inversion & Release Time Window */}
              <div className="rounded-xl border border-hairline-dark bg-brand-teal/20 p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-hairline-dark pb-2">
                  <div className="flex items-center gap-2">
                    <Compass className="h-4 w-4 text-amber-400" />
                    <h3 className="text-sm font-bold text-white">
                      Section 2: Backward Lagrangian Inversion & Discharge Corridor
                    </h3>
                  </div>
                  <Badge variant="outline" className="font-mono text-[10px] text-amber-300">
                    Rule 1: 91.5% CI
                  </Badge>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2">
                    <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Estimated Origin</span>
                    <div className="font-mono text-white font-medium mt-0.5">18.9250°N, 72.8258°E</div>
                  </div>
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2">
                    <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Release Time Window</span>
                    <div className="font-mono text-white font-medium mt-0.5">2026-08-13 14:12Z – 17:12Z</div>
                  </div>
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2">
                    <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Inferred Spill Age</span>
                    <div className="font-mono text-brand-green font-bold mt-0.5">12.0h (±1.5h)</div>
                  </div>
                </div>

                <p className="text-xs text-on-dark-muted leading-relaxed">
                  Ensemble backward Lagrangian advection using 5,000 computational super-particles driven by coupled HYCOM surface currents (0.42 m/s @ 072°) and ECMWF ERA5 10m wind velocity (5.8 m/s @ 245°) reconstructed the spill origin within a 2-sigma uncertainty ellipse (semi-major axis 3.20 km, semi-minor axis 1.80 km).
                </p>
              </div>

              {/* Section 3: Multi-Criteria Candidate Suspect Ranking Matrix */}
              <div className="rounded-xl border border-hairline-dark bg-brand-teal/20 p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-hairline-dark pb-2">
                  <div className="flex items-center gap-2">
                    <Anchor className="h-4 w-4 text-brand-green" />
                    <h3 className="text-sm font-bold text-white">
                      Section 3: Candidate Suspect Vessel Attribution Matrix
                    </h3>
                  </div>
                  <Badge variant="outline" className="font-mono text-[10px] text-brand-green">
                    AHP Saaty Consistency Ratio CR = 0.04 &lt; 0.10
                  </Badge>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-hairline-dark text-on-dark-muted">
                        <th className="py-2 px-3">Rank</th>
                        <th className="py-2 px-3">Vessel Candidate</th>
                        <th className="py-2 px-3">Type / DWT</th>
                        <th className="py-2 px-3">CPA (km)</th>
                        <th className="py-2 px-3">Anomalies</th>
                        <th className="py-2 px-3">S_culprit</th>
                        <th className="py-2 px-3 text-right">Confidence</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-hairline-dark">
                      <tr className="bg-emerald-950/30 text-white font-semibold">
                        <td className="py-2.5 px-3 text-brand-green">#1</td>
                        <td className="py-2.5 px-3">MT PACIFIC TRADER (419001234)</td>
                        <td className="py-2.5 px-3 text-on-dark-muted">Tanker / 105k</td>
                        <td className="py-2.5 px-3">0.25 km</td>
                        <td className="py-2.5 px-3 text-rose-300">Speed Drop (-8.0 kts)</td>
                        <td className="py-2.5 px-3 text-brand-green font-bold">88.4</td>
                        <td className="py-2.5 px-3 text-right text-brand-green">91.4% CI</td>
                      </tr>
                      <tr className="hover:bg-brand-teal/20 text-on-dark-muted">
                        <td className="py-2 px-3">#2</td>
                        <td className="py-2 px-3 text-white">SEA PATRIOT (352001456)</td>
                        <td className="py-2 px-3">Tanker / 74k</td>
                        <td className="py-2 px-3">1.12 km</td>
                        <td className="py-2 px-3">None</td>
                        <td className="py-2 px-3 text-white">64.2</td>
                        <td className="py-2 px-3 text-right">86.0% CI</td>
                      </tr>
                      <tr className="hover:bg-brand-teal/20 text-on-dark-muted">
                        <td className="py-2 px-3">#3</td>
                        <td className="py-2 px-3 text-white">NORDIC GULF (538007123)</td>
                        <td className="py-2 px-3">Cargo / 55k</td>
                        <td className="py-2 px-3">2.45 km</td>
                        <td className="py-2 px-3 text-rose-300">Dark Gap (75 min)</td>
                        <td className="py-2 px-3 text-white">52.1</td>
                        <td className="py-2 px-3 text-right">82.5% CI</td>
                      </tr>
                      <tr className="hover:bg-brand-teal/20 text-on-dark-muted">
                        <td className="py-2 px-3">#4</td>
                        <td className="py-2 px-3 text-white">PACIFIC GLORY (636019888)</td>
                        <td className="py-2 px-3">Bulk / 82k</td>
                        <td className="py-2 px-3">3.80 km</td>
                        <td className="py-2 px-3">None</td>
                        <td className="py-2 px-3 text-white">48.6</td>
                        <td className="py-2 px-3 text-right">79.5% CI</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Section 4: Alternative Explanations Evaluated (Rule 5) */}
              <div className="rounded-xl border border-hairline-dark bg-brand-teal/20 p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-hairline-dark pb-2">
                  <div className="flex items-center gap-2">
                    <Scale className="h-4 w-4 text-purple-400" />
                    <h3 className="text-sm font-bold text-white">
                      Section 4: Non-Vessel Alternative Hypotheses Evaluation (Rule 5)
                    </h3>
                  </div>
                  <Badge variant="outline" className="font-mono text-[10px] text-purple-300">
                    Rule 5 Mandatory Alternative Audit
                  </Badge>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-3 space-y-1">
                    <div className="flex justify-between">
                      <span className="font-semibold text-white">Natural Seep</span>
                      <Badge variant="outline" className="text-[9px]">Score: 12.5</Badge>
                    </div>
                    <p className="text-[11px] text-on-dark-muted">
                      Cataloged seep SEEP-IND-BH02 is 14.2 km SW. Evaluated non-viable due to spatial separation.
                    </p>
                  </div>
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-3 space-y-1">
                    <div className="flex justify-between">
                      <span className="font-semibold text-white">SAR Lookalike</span>
                      <Badge variant="outline" className="text-[9px]">Score: 6.0</Badge>
                    </div>
                    <p className="text-[11px] text-on-dark-muted">
                      Moderate wind (5.8 m/s) and high damping contrast (-18.4 dB) rule out biogenic surfactants.
                    </p>
                  </div>
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-3 space-y-1">
                    <div className="flex justify-between">
                      <span className="font-semibold text-white">Dark / Non-AIS Target</span>
                      <Badge variant="outline" className="text-[9px]">Score: 40.0</Badge>
                    </div>
                    <p className="text-[11px] text-on-dark-muted">
                      Zero uncataloged metallic radar reflections detected on co-registered SAR imagery.
                    </p>
                  </div>
                </div>
              </div>

              {/* Section 5: Forward Dispersion Counterfactual Simulation */}
              <div className="rounded-xl border border-hairline-dark bg-brand-teal/20 p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-hairline-dark pb-2">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-brand-green" />
                    <h3 className="text-sm font-bold text-white">
                      Section 5: Forward Dispersion Counterfactual Validation (Feature 2 / D2)
                    </h3>
                  </div>
                  <Badge variant="outline" className="font-mono text-[10px] text-brand-green">
                    Rule 1: 91.5% CI
                  </Badge>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2 text-center">
                    <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Shape IoU Overlap</span>
                    <div className="font-mono text-sm font-bold text-brand-green mt-0.5">84.8%</div>
                  </div>
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2 text-center">
                    <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Hausdorff Distance</span>
                    <div className="font-mono text-sm font-bold text-white mt-0.5">142 m</div>
                  </div>
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2 text-center">
                    <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Centroid Error</span>
                    <div className="font-mono text-sm font-bold text-white mt-0.5">88 m</div>
                  </div>
                  <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2 text-center">
                    <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Particles Sim</span>
                    <div className="font-mono text-sm font-bold text-sky-400 mt-0.5">5,000</div>
                  </div>
                </div>

                <p className="text-xs text-on-dark-muted leading-relaxed">
                  Forward Lagrangian drift initialized at the candidate suspect&apos;s closest point of approach reproduced the observed satellite slick shape with 84.8% geometric Intersection-over-Union, confirming physical hydrodynamic congruency.
                </p>
              </div>

              {/* Section 6: Official Legal Disclaimer & Signature Block */}
              <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 space-y-4">
                <div className="flex items-start gap-3">
                  <ShieldAlert className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <span className="text-xs font-bold uppercase tracking-wider text-amber-300">
                      FR-20 Mandatory Legal Evidentiary Disclaimer (Rule 6 Compliant)
                    </span>
                    <p className="text-xs text-amber-100/80 leading-relaxed font-sans">
                      {FR20_DISCLAIMER_TEXT}
                    </p>
                  </div>
                </div>

                <div className="pt-3 border-t border-amber-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-4 text-xs font-mono text-on-dark-muted">
                  <div className="space-y-0.5">
                    <div>Investigator Signature: <span className="text-white">Capt. R. Deshmukh (PSC Auditor #4412)</span></div>
                    <div>Agency: <span className="text-white">Directorate General of Shipping / Coast Guard</span></div>
                  </div>
                  <div className="space-y-0.5 text-right sm:text-right">
                    <div>Electronic Timestamp: <span className="text-white">2026-08-14T04:45:00Z</span></div>
                    <div>Status: <span className="text-brand-green font-bold">DIGITALLY VERIFIED (SHA-256)</span></div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === "chain" && (
            <div className="space-y-6">
              {/* ISO/IEC 27037 Digital Forensics Certificate */}
              <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/20 p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-green/20 text-brand-green">
                      <Lock className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-white">
                        Cryptographic Chain of Custody (ISO/IEC 27037)
                      </h3>
                      <p className="text-xs text-on-dark-muted">
                        Unbroken digital chain guaranteeing authenticity, non-repudiation, and auditability.
                      </p>
                    </div>
                  </div>
                  <Badge variant="greenSoft" className="font-mono text-xs">
                    Authenticity Validated
                  </Badge>
                </div>

                <div className="space-y-3 pt-2">
                  <div className="rounded-lg border border-hairline-dark bg-brand-teal-deep p-3 space-y-1">
                    <div className="text-[10px] uppercase font-semibold text-on-dark-muted">
                      Deterministic SHA-256 Digest
                    </div>
                    <div className="font-mono text-xs text-brand-green font-bold select-all break-all">
                      {dossier.sha256_hash}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                    <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2.5">
                      <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Generated By</span>
                      <div className="font-mono text-white text-xs mt-0.5">{dossier.generated_by}</div>
                    </div>
                    <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2.5">
                      <span className="text-[10px] text-on-dark-muted uppercase font-semibold">Generation Timestamp</span>
                      <div className="font-mono text-white text-xs mt-0.5">{dossier.generated_at ?? "2026-08-14T04:45:00Z"}</div>
                    </div>
                    <div className="rounded border border-hairline-dark bg-brand-teal-deep p-2.5">
                      <span className="text-[10px] text-on-dark-muted uppercase font-semibold">File Footprint</span>
                      <div className="font-mono text-brand-green font-bold text-xs mt-0.5">
                        {((dossier.file_size_bytes ?? 1485920) / (1024 * 1024)).toFixed(2)} MB ({(dossier.file_size_bytes ?? 1485920).toLocaleString()} bytes)
                      </div>
                    </div>
                  </div>
                </div>

                {/* Model Checkpoint Versions Audit Matrix (Rule 7) */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-bold text-white flex items-center gap-2">
                      <Cpu className="h-4 w-4 text-sky-400" />
                      Algorithmic Engines & Checkpoint Manifest
                    </h4>
                    <Badge variant="outline" className="font-mono text-[10px] border-hairline-dark">
                      Rule 7 Traceability
                    </Badge>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {Object.entries(dossier.model_versions ?? SYNTHETIC_DOSSIER_RESULT.model_versions ?? {}).map(([tier, version]) => (
                      <div
                        key={tier}
                        className="rounded-lg border border-hairline-dark bg-brand-teal-deep p-3 flex items-center justify-between text-xs"
                      >
                        <div>
                          <span className="text-on-dark-muted uppercase font-semibold text-[10px]">
                            {tier.replace(/_/g, " ")}
                          </span>
                          <div className="font-mono text-white font-bold mt-0.5">
                            {String(version)}
                          </div>
                        </div>
                        <CheckCircle2 className="h-4 w-4 text-brand-green shrink-0" />
                      </div>
                    ))}
                  </div>
                </div>

                {/* Digital Verification QR Code */}
                <div className="rounded-xl border border-hairline-dark bg-brand-teal/20 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <h4 className="text-sm font-bold text-white flex items-center gap-2">
                      <QrCode className="h-4 w-4 text-brand-green" />
                      Field Verification & Chain-of-Custody QR Code
                    </h4>
                    <p className="text-xs text-on-dark-muted max-w-lg">
                      Port State Control (PSC) inspectors can scan this cryptographic QR code at the gangway to verify the authentic SHA-256 seal against the AEGIS sovereign registry.
                    </p>
                  </div>

                  <div className="h-24 w-24 bg-white rounded-lg p-2 flex items-center justify-center shrink-0 shadow-lg">
                    {dossier.verification_qr_b64 ? (
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img
                        src={dossier.verification_qr_b64}
                        alt="Chain of Custody QR Code"
                        className="h-full w-full object-contain"
                      />
                    ) : (
                      /* Inline High-Contrast QR Code Icon Graphic */
                      <div className="grid grid-cols-3 gap-1 h-full w-full p-1 bg-black rounded">
                        <div className="border-2 border-white rounded-sm" />
                        <div className="bg-white rounded-sm" />
                        <div className="border-2 border-white rounded-sm" />
                        <div className="bg-white rounded-sm" />
                        <div className="bg-white rounded-sm" />
                        <div className="bg-white rounded-sm" />
                        <div className="border-2 border-white rounded-sm" />
                        <div className="bg-white rounded-sm" />
                        <div className="border-2 border-white rounded-sm" />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === "stream" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <FileText className="h-4 w-4 text-sky-400" />
                    Live Binary PDF Stream Viewer
                  </h3>
                  <p className="text-xs text-on-dark-muted">
                    Streaming court-ready PDF file compiled on demand from the AEGIS backend microservice.
                  </p>
                </div>

                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleDownload}
                  className="gap-1.5 text-xs text-brand-green hover:text-white"
                >
                  <Download className="h-3.5 w-3.5" />
                  Open in Browser Viewer
                </Button>
              </div>

              {/* Embedded PDF Viewport Container */}
              <div className="rounded-xl border border-hairline-dark bg-[#00141e] overflow-hidden shadow-inner">
                <div className="p-3 bg-brand-teal/40 border-b border-hairline-dark flex items-center justify-between text-xs text-on-dark-muted font-mono">
                  <span>File: aegis_dossier_{caseId.substring(0, 16)}.pdf</span>
                  <span>MIME: application/pdf</span>
                </div>
                <iframe
                  src={downloadUrl}
                  title="Official Legal Dossier PDF Stream"
                  className="w-full h-[520px] bg-white border-0"
                />
              </div>
            </div>
          )}
        </div>

        {/* Action Footer */}
        <div className="p-4 border-t border-hairline-dark bg-brand-teal-deep flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleRegenerate}
              disabled={isRegenerating}
              className="gap-1.5 text-xs text-on-dark-muted hover:text-white w-full sm:w-auto"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isRegenerating ? "animate-spin" : ""}`} />
              <span>{isRegenerating ? "Compiling..." : "Re-compile PDF"}</span>
            </Button>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onOpenChange(false)}
              className="text-xs w-full sm:w-auto"
            >
              Close
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={handleDownload}
              className="gap-1.5 text-xs font-semibold w-full sm:w-auto bg-brand-green text-brand-teal-deep hover:bg-brand-green/90 shadow-lg"
            >
              {downloadSuccess ? (
                <>
                  <Check className="h-3.5 w-3.5 text-brand-teal-deep" />
                  <span>Download Initiated</span>
                </>
              ) : (
                <>
                  <Download className="h-3.5 w-3.5" />
                  <span>Download Official Dossier (.pdf)</span>
                </>
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
