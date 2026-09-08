"use client";

import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Radar, Download, ShieldCheck, Layers } from "lucide-react";

export interface SarChipModalProps {
  isOpen: boolean;
  onClose: () => void;
  caseId: string;
  sceneRef?: string;
  regionName?: string;
  sensor?: string;
  detectionTime?: string;
  slickAreaM2?: number;
  confidencePct?: number;
}

export function SarChipModal({
  isOpen,
  onClose,
  caseId,
  sceneRef = "S1A_IW_GRDH_1SDV_20260814T034215_045123_055678_B42A",
  regionName = "Offshore Mumbai High Corridor",
  sensor = "Sentinel-1A C-SAR IW",
  detectionTime = "2026-08-14T03:42:00Z",
  slickAreaM2 = 5_240_000,
  confidencePct = 92.4,
}: SarChipModalProps) {
  const areaKm2 = (slickAreaM2 / 1_000_000).toFixed(2);

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl bg-brand-teal-deep border border-hairline-dark text-white p-6 shadow-2xl">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Badge variant="purple" className="text-xs">
              Copernicus Synthetic Aperture Radar
            </Badge>
            <Badge variant="outline" className="font-mono text-xs text-on-dark-muted">
              {caseId}
            </Badge>
          </div>
          <DialogTitle className="text-xl font-bold text-white mt-2 flex items-center gap-2">
            <Radar className="h-5 w-5 text-brand-green" />
            Calibrated SAR Detection Imagery Chip
          </DialogTitle>
          <DialogDescription className="text-sm text-on-dark-muted">
            Calibrated radar backscatter (&sigma;&deg;) crop exhibiting capillary wave damping and automated slick delineation.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 py-4">
          {/* Radar Imagery Chip Canvas Preview */}
          <div className="flex flex-col items-center justify-center">
            <div className="relative overflow-hidden rounded-xl border border-hairline-dark bg-[#081219] p-2 shadow-inner w-full max-w-[280px] aspect-square flex items-center justify-center">
              {/* SVG Calibrated SAR Chip */}
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 256 256"
                className="w-full h-full rounded-lg shadow-lg"
              >
                <defs>
                  <radialGradient id="sar-bg" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stopColor="#192a38" />
                    <stop offset="100%" stopColor="#09141c" />
                  </radialGradient>
                  <filter id="sar-speckle">
                    <feTurbulence
                      type="fractalNoise"
                      baseFrequency="0.65"
                      numOctaves="3"
                      result="noise"
                    />
                    <feColorMatrix
                      type="matrix"
                      values="0.2 0 0 0 0  0 0.25 0 0 0  0 0 0.3 0 0  0 0 0 0.4 0"
                    />
                    <feBlend in="SourceGraphic" in2="noise" mode="screen" />
                  </filter>
                </defs>
                <rect width="256" height="256" fill="url(#sar-bg)" />
                <rect width="256" height="256" filter="url(#sar-speckle)" opacity="0.85" />

                {/* Dark slick footprint (wave damping signature) */}
                <path
                  d="M 64,88 Q 90,60 138,72 T 196,118 Q 204,164 162,188 T 92,176 Q 52,142 64,88 Z"
                  fill="#000e17"
                  fillOpacity="0.88"
                  stroke="#00ed64"
                  strokeWidth="2.5"
                  strokeDasharray="4,2"
                />
                <path
                  d="M 82,104 Q 106,84 142,92 T 178,126 Q 184,156 150,170 T 106,160 Q 76,134 82,104 Z"
                  fill="#00060c"
                  fillOpacity="0.95"
                  stroke="#00a35c"
                  strokeWidth="1.5"
                />

                {/* Telemetry Overlays on Chip */}
                <rect
                  x="8"
                  y="8"
                  width="128"
                  height="20"
                  rx="4"
                  fill="#001e2b"
                  fillOpacity="0.85"
                  stroke="#1c2d38"
                  strokeWidth="1"
                />
                <text
                  x="14"
                  y="22"
                  fontFamily="monospace"
                  fontSize="9"
                  fill="#00ed64"
                  fontWeight="bold"
                >
                  &sigma;&deg; -24.5 dB (VV)
                </text>

                <rect
                  x="8"
                  y="228"
                  width="156"
                  height="20"
                  rx="4"
                  fill="#001e2b"
                  fillOpacity="0.85"
                  stroke="#1c2d38"
                  strokeWidth="1"
                />
                <text
                  x="14"
                  y="242"
                  fontFamily="monospace"
                  fontSize="8"
                  fill="#a8b3bc"
                >
                  Sentinel-1A C-SAR IW
                </text>
              </svg>

              <div className="absolute top-4 right-4">
                <Badge variant="green" className="text-[10px] font-mono">
                  Damped
                </Badge>
              </div>
            </div>

            {/* Scale Bar & Contrast Gauge */}
            <div className="mt-3 flex items-center justify-between w-full max-w-[280px] text-[10px] font-mono text-on-dark-muted">
              <span>-28 dB (Oil Slick)</span>
              <div className="h-1.5 w-24 rounded-full bg-gradient-to-r from-[#000e17] via-[#00a35c] to-brand-green" />
              <span>-8 dB (Clean Sea)</span>
            </div>
          </div>

          {/* Calibrated Forensic Metadata Breakdown */}
          <div className="space-y-3 text-xs">
            <div className="rounded-lg border border-hairline-dark bg-white/5 p-3 space-y-2">
              <div className="flex justify-between">
                <span className="text-on-dark-muted">Satellite Sensor:</span>
                <span className="font-medium text-white">{sensor}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-on-dark-muted">Detection Time:</span>
                <span className="font-mono font-medium text-brand-green">
                  {detectionTime.replace("T", " ").replace("Z", " UTC")}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-on-dark-muted">Geographic Region:</span>
                <span className="font-medium text-white">{regionName}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-on-dark-muted">Slick Area Footprint:</span>
                <span className="font-mono font-medium text-white">
                  {areaKm2} km&sup2; ({slickAreaM2.toLocaleString()} m&sup2;)
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-on-dark-muted">Damping Contrast:</span>
                <span className="font-mono font-medium text-brand-green">&Delta;&sigma;&deg; = 12.4 dB</span>
              </div>
            </div>

            {/* Copernicus Scene Reference */}
            <div className="rounded-lg border border-hairline-dark bg-brand-teal-deep p-2.5">
              <div className="text-[10px] uppercase font-bold text-on-dark-muted mb-1 flex items-center gap-1.5">
                <Layers className="h-3 w-3 text-brand-green" />
                Copernicus Scene Product
              </div>
              <div className="font-mono text-[10px] text-brand-green-soft break-all select-all">
                {sceneRef}
              </div>
            </div>

            {/* Rule 1 Paired Confidence Indicator */}
            <div className="flex items-center justify-between rounded-lg border border-hairline-dark bg-white/5 p-2.5">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-brand-green" />
                <span className="font-semibold text-white">Detection Confidence</span>
              </div>
              <Badge variant="green" className="font-mono">
                {confidencePct.toFixed(1)}% CI
              </Badge>
            </div>
          </div>
        </div>

        {/* Modal Action Controls */}
        <div className="flex items-center justify-between pt-3 border-t border-hairline-dark">
          <div className="text-[11px] font-mono text-on-dark-muted">
            Calibrated Level-1 GRDH Product &bull; 10m Ground Resolution
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                const link = document.createElement("a");
                link.href = `/api/v1/cases/${caseId}/detection/sar-chip`;
                link.download = `sar-chip-${caseId}.svg`;
                link.click();
              }}
            >
              <Download className="h-3.5 w-3.5" />
              Download Chip
            </Button>
            <Button variant="default" size="sm" onClick={onClose}>
              Close Preview
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default SarChipModal;
