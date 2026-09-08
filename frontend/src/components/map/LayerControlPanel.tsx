"use client";

import * as React from "react";
import { Layers, ChevronDown, ChevronUp, Eye, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

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
      className={`rounded-xl border border-hairline-dark bg-brand-teal-deep/90 p-3 shadow-xl backdrop-blur-md text-white transition-all ${className}`}
    >
      {/* Panel Header */}
      <div className="flex items-center justify-between gap-3 pb-2 border-b border-hairline-dark">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-brand-green" />
          <span className="text-xs font-bold uppercase tracking-wider text-white">
            Geospatial Overlays
          </span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0 text-on-dark-muted hover:text-white"
          onClick={() => setIsOpen(!isOpen)}
        >
          {isOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </Button>
      </div>

      {/* Layer Toggles */}
      {isOpen && (
        <div className="mt-3 space-y-2 text-xs">
          {/* 1. Bathymetry Depth Contours */}
          <button
            type="button"
            onClick={() => onToggleLayer("bathymetry")}
            className="flex w-full items-center justify-between rounded-lg p-2 transition-colors hover:bg-white/5"
          >
            <div className="flex items-center gap-2">
              {layers.bathymetry ? (
                <Eye className="h-3.5 w-3.5 text-brand-green" />
              ) : (
                <EyeOff className="h-3.5 w-3.5 text-on-dark-muted" />
              )}
              <span className={layers.bathymetry ? "text-white font-medium" : "text-on-dark-muted"}>
                Bathymetry Contours
              </span>
            </div>
            <Badge variant={layers.bathymetry ? "greenSoft" : "outline"} className="text-[10px]">
              50-1000m
            </Badge>
          </button>

          {/* 2. EEZ Maritime Limits */}
          <button
            type="button"
            onClick={() => onToggleLayer("eez")}
            className="flex w-full items-center justify-between rounded-lg p-2 transition-colors hover:bg-white/5"
          >
            <div className="flex items-center gap-2">
              {layers.eez ? (
                <Eye className="h-3.5 w-3.5 text-accent-blue" />
              ) : (
                <EyeOff className="h-3.5 w-3.5 text-on-dark-muted" />
              )}
              <span className={layers.eez ? "text-white font-medium" : "text-on-dark-muted"}>
                UNCLOS EEZ Limits
              </span>
            </div>
            <Badge variant={layers.eez ? "blue" : "outline"} className="text-[10px]">
              200 NM
            </Badge>
          </button>

          {/* 3. Shipping Lanes (TSS) */}
          <button
            type="button"
            onClick={() => onToggleLayer("shippingLanes")}
            className="flex w-full items-center justify-between rounded-lg p-2 transition-colors hover:bg-white/5"
          >
            <div className="flex items-center gap-2">
              {layers.shippingLanes ? (
                <Eye className="h-3.5 w-3.5 text-accent-orange" />
              ) : (
                <EyeOff className="h-3.5 w-3.5 text-on-dark-muted" />
              )}
              <span className={layers.shippingLanes ? "text-white font-medium" : "text-on-dark-muted"}>
                Shipping Lanes (TSS)
              </span>
            </div>
            <Badge variant={layers.shippingLanes ? "orange" : "outline"} className="text-[10px]">
              IMO Corridors
            </Badge>
          </button>

          {/* 4. Marine Protected Areas */}
          <button
            type="button"
            onClick={() => onToggleLayer("mpa")}
            className="flex w-full items-center justify-between rounded-lg p-2 transition-colors hover:bg-white/5"
          >
            <div className="flex items-center gap-2">
              {layers.mpa ? (
                <Eye className="h-3.5 w-3.5 text-brand-green" />
              ) : (
                <EyeOff className="h-3.5 w-3.5 text-on-dark-muted" />
              )}
              <span className={layers.mpa ? "text-white font-medium" : "text-on-dark-muted"}>
                Protected Marine Areas
              </span>
            </div>
            <Badge variant={layers.mpa ? "green" : "outline"} className="text-[10px]">
              Zero-Discharge
            </Badge>
          </button>
        </div>
      )}
    </div>
  );
}
