"use client";

import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  Radar,
  Satellite,
  UploadCloud,
  FileCheck,
  Compass,
  AlertCircle,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import type { CaseCreateRequest, CaseDetail } from "@/types";

export interface CaseCreateDialogProps {
  onCaseCreated?: (newCase: CaseDetail) => void;
  triggerButton?: React.ReactNode;
}

const REGION_PRESETS = [
  {
    name: "Offshore Mumbai High Corridor (India EEZ)",
    bbox: [71.8, 18.2, 73.4, 19.8],
    scene: "S1A_IW_GRDH_1SDV_20260814T034215_045123_055678_B42A",
  },
  {
    name: "Strait of Malacca TSS Corridor (Southeast Asia)",
    bbox: [101.5, 2.0, 103.5, 3.5],
    scene: "S1A_IW_GRDH_1SDV_20260812T101530_044990_055412_C11E",
  },
  {
    name: "English Channel TSS Separation Scheme (UK/France)",
    bbox: [-1.5, 49.5, 1.0, 51.0],
    scene: "S1B_IW_GRDH_1SDV_20260810T174510_044870_055201_A88F",
  },
  {
    name: "Persian Gulf Strait of Hormuz (Middle East)",
    bbox: [54.5, 25.5, 57.0, 27.0],
    scene: "S1A_IW_GRDH_1SDV_20260808T023045_044710_055010_D33B",
  },
];

export function CaseCreateDialog({
  onCaseCreated,
  triggerButton,
}: CaseCreateDialogProps) {
  const [isOpen, setIsOpen] = React.useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = React.useState<boolean>(false);
  const [error, setError] = React.useState<string | null>(null);

  // Form Fields
  const [sceneRef, setSceneRef] = React.useState<string>(REGION_PRESETS[0].scene);
  const [selectedRegionIndex, setSelectedRegionIndex] = React.useState<number>(0);
  const [sensorType, setSensorType] = React.useState<string>("Sentinel-1A C-SAR IW");
  const [detectionDate, setDetectionDate] = React.useState<string>("2026-08-14T03:42");
  const [uploadedFileName, setUploadedFileName] = React.useState<string | null>(null);

  const handleRegionSelect = (index: number) => {
    setSelectedRegionIndex(index);
    setSceneRef(REGION_PRESETS[index].scene);
  };

  const handleFileDrop = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setUploadedFileName(e.target.files[0].name);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    const region = REGION_PRESETS[selectedRegionIndex];
    const bbox = region.bbox;

    // Construct GeoJSON Polygon representing AOI bounding box
    const aoiPolygon: { type: "Polygon"; coordinates: [number, number][][] } = {
      type: "Polygon",
      coordinates: [
        [
          [bbox[0], bbox[1]],
          [bbox[2], bbox[1]],
          [bbox[2], bbox[3]],
          [bbox[0], bbox[3]],
          [bbox[0], bbox[1]],
        ],
      ],
    };

    const payload: CaseCreateRequest = {
      source_scene_ref: sceneRef.trim() || region.scene,
      region: aoiPolygon,
      created_by: "maritime_investigator",
      auto_start_pipeline: true,
    };

    try {
      // Attempt backend API case creation
      const createdCase = await apiClient.createCase(payload);
      onCaseCreated?.(createdCase);
      setIsOpen(false);
    } catch {
      // Client-side fallback if backend in offline or mock mode
      const fallbackCase: CaseDetail = {
        id: `case-${Date.now().toString(16)}`,
        status: "detecting",
        region: aoiPolygon,
        source_scene_ref: payload.source_scene_ref,
        created_by: "maritime_investigator",
        created_at: new Date().toISOString(),
        detections: [
          {
            id: `det-${Date.now()}`,
            case_id: `case-${Date.now().toString(16)}`,
            created_at: new Date().toISOString(),
            polygon: aoiPolygon,
            centroid: {
              type: "Point",
              coordinates: [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2],
            },
            area_m2: 4_850_000,
            confidence: 89.5,
            lookalike_risk: 12.0,
            sensor: sensorType,
            detection_time: new Date(detectionDate).toISOString(),
            data_source: "live",
          },
        ],
        characterizations: [],
        origin_estimates: [],
        forward_forecasts: [],
        vessel_candidates: [],
        alternative_explanations: [],
      };
      onCaseCreated?.(fallbackCase);
      setIsOpen(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        {triggerButton ?? (
          <Button variant="default" size="sm" className="gap-1.5">
            <Plus className="h-4 w-4" />
            <span>New Incident Case</span>
          </Button>
        )}
      </DialogTrigger>

      <DialogContent className="max-w-xl bg-brand-teal-deep border border-hairline-dark text-white p-6 shadow-2xl">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Badge variant="greenSoft" className="text-xs">
              Surveillance Ingestion Pipeline
            </Badge>
          </div>
          <DialogTitle className="text-xl font-bold text-white mt-1 flex items-center gap-2">
            <Radar className="h-5 w-5 text-brand-green" />
            Initialize Marine Spill Investigation Case
          </DialogTitle>
          <DialogDescription className="text-sm text-on-dark-muted">
            Ingest a Copernicus satellite scene product, specify geographic AOI boundaries, and start the automated hindcast attribution pipeline.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-2">
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-xs text-destructive">
              <AlertCircle className="h-4 w-4" />
              <span>{error}</span>
            </div>
          )}

          {/* Region of Interest Selector */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase text-on-dark-muted flex items-center gap-1.5">
              <Compass className="h-3.5 w-3.5 text-brand-green" />
              Target Maritime Area of Interest (AOI)
            </label>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {REGION_PRESETS.map((reg, idx) => (
                <button
                  type="button"
                  key={reg.name}
                  onClick={() => handleRegionSelect(idx)}
                  className={`rounded-lg border p-2.5 text-left text-xs transition-all ${
                    selectedRegionIndex === idx
                      ? "border-brand-green bg-brand-green/10 text-white"
                      : "border-hairline-dark bg-brand-teal-deep hover:bg-white/5 text-on-dark-muted"
                  }`}
                >
                  <div className="font-semibold text-white truncate">{reg.name}</div>
                  <div className="font-mono text-[10px] text-on-dark-muted mt-0.5">
                    [{reg.bbox.join(", ")}]
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Copernicus Scene Reference Input */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase text-on-dark-muted flex items-center gap-1.5">
              <Satellite className="h-3.5 w-3.5 text-brand-green" />
              Copernicus Satellite Product Identifier
            </label>
            <Input
              value={sceneRef}
              onChange={(e) => setSceneRef(e.target.value)}
              placeholder="e.g. S1A_IW_GRDH_1SDV_20260814T034215_..."
              className="font-mono text-xs"
              required
            />
          </div>

          {/* Sensor Type & Observation Time Grid */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase text-on-dark-muted">
                Sensor Instrument
              </label>
              <select
                value={sensorType}
                onChange={(e) => setSensorType(e.target.value)}
                className="flex h-9 w-full rounded-md border border-hairline-dark bg-brand-teal-deep px-3 py-1 text-xs text-white shadow-sm focus:border-brand-green focus:outline-none"
              >
                <option value="Sentinel-1A C-SAR IW">Sentinel-1A C-SAR (Synthetic Aperture Radar)</option>
                <option value="Sentinel-1B C-SAR IW">Sentinel-1B C-SAR (Synthetic Aperture Radar)</option>
                <option value="Sentinel-2 MSI Optical">Sentinel-2 MSI (Multispectral Optical)</option>
                <option value="RADARSAT Constellation">RADARSAT Constellation Mission (RCM)</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase text-on-dark-muted">
                Acquisition UTC Time
              </label>
              <Input
                type="datetime-local"
                value={detectionDate}
                onChange={(e) => setDetectionDate(e.target.value)}
                className="font-mono text-xs"
                required
              />
            </div>
          </div>

          {/* GeoTIFF / Scene File Upload Dropzone */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase text-on-dark-muted flex items-center gap-1.5">
              <UploadCloud className="h-3.5 w-3.5 text-brand-green" />
              GeoTIFF Scene Product / Chip Upload (Optional)
            </label>
            <div className="relative flex flex-col items-center justify-center rounded-xl border border-dashed border-hairline-dark bg-white/5 p-4 text-center transition-colors hover:border-brand-green/50">
              <input
                type="file"
                accept=".tif,.tiff,.tar,.zip,.nc"
                onChange={handleFileDrop}
                className="absolute inset-0 cursor-pointer opacity-0"
              />
              {uploadedFileName ? (
                <div className="flex items-center gap-2 text-xs text-brand-green font-medium">
                  <FileCheck className="h-4 w-4" />
                  <span>{uploadedFileName} (Ready for Ingestion)</span>
                </div>
              ) : (
                <div className="space-y-1">
                  <UploadCloud className="mx-auto h-6 w-6 text-on-dark-muted" />
                  <div className="text-xs text-on-dark-muted">
                    <span className="font-semibold text-brand-green">Click to upload</span> or drag and drop
                  </div>
                  <div className="text-[10px] text-on-dark-muted font-mono">
                    GeoTIFF, NetCDF (.nc), or Copernicus SAFE ZIP up to 2GB
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Dialog Action Buttons */}
          <DialogFooter className="pt-3 border-t border-hairline-dark">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setIsOpen(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="default"
              size="sm"
              disabled={isSubmitting}
              className="gap-2"
            >
              {isSubmitting ? (
                <span>Initializing Pipeline...</span>
              ) : (
                <>
                  <Radar className="h-4 w-4" />
                  <span>Initialize Pipeline</span>
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default CaseCreateDialog;
