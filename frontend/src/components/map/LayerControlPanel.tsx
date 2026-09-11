"use client";

import * as React from "react";
import { Layers, ChevronDown, ChevronUp } from "lucide-react";

export interface LayerVisibilityState {
  bathymetry: boolean;
  eez: boolean;
  shippingLanes: boolean;
  mpa: boolean;
  sarDetection?: boolean;
}

export interface LayerControlPanelProps {
  layers: LayerVisibilityState;
  onToggleLayer: (layerKey: keyof LayerVisibilityState) => void;
  className?: string;
}

export function LayerControlPanel({
  layers,
  onToggleLayer,
  className = "",
}: LayerControlPanelProps) {
  const [isOpen, setIsOpen] = React.useState<boolean>(true);

  return (
    <div
      className={`rounded-sm border border-[#1F2937] bg-[#161F2C]/90 p-3 shadow-2xl backdrop-blur-md text-white transition-all font-mono min-w-[260px] ${className}`}
    >
      {/* Panel Header */}
      <div className="flex items-center justify-between gap-3 pb-2 border-b border-[#1F2937]">
        <div className="flex items-center gap-2">
          <Layers className="h-3.5 w-3.5 text-emerald-400" />
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-300">
            GEOSPATIAL OVERLAYS
          </span>
        </div>
        <button
          type="button"
          className="h-5 w-5 flex items-center justify-center text-slate-400 hover:text-white"
          onClick={() => setIsOpen(!isOpen)}
        >
          {isOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </button>
      </div>

      {/* GIS Authentic Layer List */}
      {isOpen && (
        <div className="mt-2 space-y-1 text-xs">
          {/* 1. Bathymetry Depth Contours */}
          <button
            type="button"
            onClick={() => onToggleLayer("bathymetry")}
            className="flex w-full items-center justify-between px-1.5 py-1 transition-colors hover:bg-slate-800/60 rounded-sm"
          >
            <div className="flex items-center gap-2.5">
              <span
                className={`flex h-3.5 w-3.5 items-center justify-center border transition-colors ${
                  layers.bathymetry
                    ? "border-emerald-500 bg-emerald-500/20 text-emerald-400"
                    : "border-slate-700 bg-slate-900"
                }`}
              >
                {layers.bathymetry && <span className="h-1.5 w-1.5 bg-emerald-400" />}
              </span>
              <span className={layers.bathymetry ? "text-slate-200" : "text-slate-500"}>
                Bathymetry Contours
              </span>
            </div>
            <span className="text-slate-400 font-mono text-[11px] tabular-nums">
              [50–1000m]
            </span>
          </button>

          {/* 2. EEZ Maritime Limits */}
          <button
            type="button"
            onClick={() => onToggleLayer("eez")}
            className="flex w-full items-center justify-between px-1.5 py-1 transition-colors hover:bg-slate-800/60 rounded-sm"
          >
            <div className="flex items-center gap-2.5">
              <span
                className={`flex h-3.5 w-3.5 items-center justify-center border transition-colors ${
                  layers.eez
                    ? "border-cyan-500 bg-cyan-500/20 text-cyan-400"
                    : "border-slate-700 bg-slate-900"
                }`}
              >
                {layers.eez && <span className="h-1.5 w-1.5 bg-cyan-400" />}
              </span>
              <span className={layers.eez ? "text-slate-200" : "text-slate-500"}>
                UNCLOS EEZ Limits
              </span>
            </div>
            <span className="text-cyan-400 font-mono text-[11px] tabular-nums">
              [200 NM]
            </span>
          </button>

          {/* 3. Shipping Lanes (TSS) */}
          <button
            type="button"
            onClick={() => onToggleLayer("shippingLanes")}
            className="flex w-full items-center justify-between px-1.5 py-1 transition-colors hover:bg-slate-800/60 rounded-sm"
          >
            <div className="flex items-center gap-2.5">
              <span
                className={`flex h-3.5 w-3.5 items-center justify-center border transition-colors ${
                  layers.shippingLanes
                    ? "border-amber-500 bg-amber-500/20 text-amber-400"
                    : "border-slate-700 bg-slate-900"
                }`}
              >
                {layers.shippingLanes && <span className="h-1.5 w-1.5 bg-amber-400" />}
              </span>
              <span className={layers.shippingLanes ? "text-slate-200" : "text-slate-500"}>
                Shipping Lanes (TSS)
              </span>
            </div>
            <span className="text-amber-400 font-mono text-[11px] tabular-nums">
              [IMO Traffic]
            </span>
          </button>

          {/* 4. Marine Protected Areas */}
          <button
            type="button"
            onClick={() => onToggleLayer("mpa")}
            className="flex w-full items-center justify-between px-1.5 py-1 transition-colors hover:bg-slate-800/60 rounded-sm"
          >
            <div className="flex items-center gap-2.5">
              <span
                className={`flex h-3.5 w-3.5 items-center justify-center border transition-colors ${
                  layers.mpa
                    ? "border-emerald-500 bg-emerald-500/20 text-emerald-400"
                    : "border-slate-700 bg-slate-900"
                }`}
              >
                {layers.mpa && <span className="h-1.5 w-1.5 bg-emerald-400" />}
              </span>
              <span className={layers.mpa ? "text-slate-200" : "text-slate-500"}>
                Protected Marine Areas
              </span>
            </div>
            <span className="text-emerald-400 font-mono text-[11px] tabular-nums">
              [Zero-Discharge]
            </span>
          </button>
        </div>
      )}
    </div>
  );
}
