"use client";

import * as React from "react";
import {
  Play,
  Pause,
  RotateCcw,
  SkipBack,
  SkipForward,
  FastForward,
  Rewind,
  Clock,
  Activity,
  Repeat,
  ShieldCheck,
} from "lucide-react";

import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

// -----------------------------------------------------------------------------
// Data Types & Contracts (Rule 1 & Rule 6 Compliant)
// -----------------------------------------------------------------------------

export interface LiveVesselRanking {
  mmsi: string;
  name: string;
  rank: number;
  isPutativeCulprit: boolean;
  score: number; // Dynamic S_culprit [0.0 - 1.0]
  cpaDistanceNm: number;
  temporalOffsetMin: number;
  confidencePct: number; // Rule 1: Mandatory paired confidence
  flag: string;
  vesselType: string;
}

export interface TimeScrubberProps {
  /** Total simulation duration in seconds (defaults to 1080s = 12 hours) */
  totalDurationSeconds?: number;
  /** Start timestamp of simulation (t_0 = t_obs - 12h) */
  startTimestamp?: string;
  /** End timestamp of simulation (t_obs satellite detection) */
  endTimestamp?: string;
  /** Externally controlled time in seconds [0, totalDurationSeconds] */
  currentTimeSeconds?: number;
  /** Callback fired whenever simulation time advances or is scrubbed */
  onTimeChange?: (currentSeconds: number, progressPct: number, currentDate: Date) => void;
  /** Callback fired when live vessel rankings update */
  onRankingsChange?: (rankings: LiveVesselRanking[]) => void;
  /** Callback fired when playback state changes */
  onPlayStateChange?: (isPlaying: boolean, isReverse: boolean) => void;
  /** Optional container CSS class */
  className?: string;
}

// -----------------------------------------------------------------------------
// Dynamic Attribution & Ranking Simulation Engine
// -----------------------------------------------------------------------------

export function computeDynamicRankings(progress: number): LiveVesselRanking[] {
  // progress in [0, 1] normalized across 12-hour hindcast
  // Candidate 1: MT PACIFIC TRADER (CPA at ~50% progress, t = 540s)
  const dist1 = Math.max(0.42, Math.abs(progress - 0.5) * 7.8);
  const score1 = Math.max(
    0.14,
    0.884 * Math.exp(-Math.pow((progress - 0.5) / 0.22, 2))
  );

  // Candidate 2: MV OCEAN STAR (CPA at ~42% progress, t = 450s)
  const dist2 = Math.max(2.15, Math.abs(progress - 0.42) * 8.6);
  const score2 = Math.max(
    0.11,
    0.485 * Math.exp(-Math.pow((progress - 0.42) / 0.28, 2))
  );

  // Candidate 3: SEABIRD EXPLORER (CPA at ~48% progress, t = 520s)
  const dist3 = Math.max(4.8, Math.abs(progress - 0.48) * 10.4);
  const score3 = Math.max(
    0.08,
    0.219 * Math.exp(-Math.pow((progress - 0.48) / 0.35, 2))
  );

  const candidates: LiveVesselRanking[] = [
    {
      mmsi: "419001234",
      name: "MT PACIFIC TRADER",
      rank: 1,
      isPutativeCulprit: true,
      score: Number(score1.toFixed(3)),
      cpaDistanceNm: Number(dist1.toFixed(2)),
      temporalOffsetMin: Math.round((progress - 0.5) * 720),
      confidencePct: 91.4,
      flag: "Panama",
      vesselType: "Crude Oil Tanker",
    },
    {
      mmsi: "563004567",
      name: "MV OCEAN STAR",
      rank: 2,
      isPutativeCulprit: false,
      score: Number(score2.toFixed(3)),
      cpaDistanceNm: Number(dist2.toFixed(2)),
      temporalOffsetMin: Math.round((progress - 0.42) * 720),
      confidencePct: 88.0,
      flag: "Singapore",
      vesselType: "Container Ship",
    },
    {
      mmsi: "412998877",
      name: "SEABIRD EXPLORER",
      rank: 3,
      isPutativeCulprit: false,
      score: Number(score3.toFixed(3)),
      cpaDistanceNm: Number(dist3.toFixed(2)),
      temporalOffsetMin: Math.round((progress - 0.48) * 720),
      confidencePct: 82.5,
      flag: "India",
      vesselType: "Offshore Supply",
    },
  ];

  // Dynamic ranking sorted by attribution score descending
  candidates.sort((a, b) => b.score - a.score);
  return candidates.map((item, index) => ({
    ...item,
    rank: index + 1,
  }));
}

// -----------------------------------------------------------------------------
// Interactive Replay Time-Scrubber Component
// -----------------------------------------------------------------------------

export function TimeScrubber({
  totalDurationSeconds = 1080,
  startTimestamp = "2026-08-13T15:42:00Z",
  endTimestamp = "2026-08-14T03:42:00Z",
  currentTimeSeconds: externalTime,
  onTimeChange,
  onRankingsChange,
  onPlayStateChange,
  className = "",
}: TimeScrubberProps) {
  // Internal clock state in seconds [0, totalDurationSeconds]
  const [internalSeconds, setInternalSeconds] = React.useState<number>(0);
  const currentSeconds = externalTime !== undefined ? externalTime : internalSeconds;

  // Playback engine states
  const [isPlaying, setIsPlaying] = React.useState<boolean>(false);
  const [isReverse, setIsReverse] = React.useState<boolean>(false);
  const [speedMultiplier, setSpeedMultiplier] = React.useState<number>(5);
  const [isLooping, setIsLooping] = React.useState<boolean>(true);

  // Time calculations
  const startDate = React.useMemo(() => new Date(startTimestamp), [startTimestamp]);
  const endDate = React.useMemo(() => new Date(endTimestamp), [endTimestamp]);
  const totalMs = React.useMemo(
    () => endDate.getTime() - startDate.getTime(),
    [startDate, endDate]
  );
  const progress = Math.min(1, Math.max(0, currentSeconds / totalDurationSeconds));
  const currentDate = React.useMemo(
    () => new Date(startDate.getTime() + progress * totalMs),
    [startDate, progress, totalMs]
  );

  // Dynamic evolving rankings at current simulation step
  const currentRankings = React.useMemo(
    () => computeDynamicRankings(progress),
    [progress]
  );
  const topCandidate = currentRankings[0];

  // Notify parent of updates
  const lastEmittedProgress = React.useRef<number>(-1);
  React.useEffect(() => {
    if (Math.abs(progress - lastEmittedProgress.current) > 0.001) {
      lastEmittedProgress.current = progress;
      onTimeChange?.(currentSeconds, progress, currentDate);
      onRankingsChange?.(currentRankings);
    }
  }, [currentSeconds, progress, currentDate, currentRankings, onTimeChange, onRankingsChange]);

  // Notify play state changes
  React.useEffect(() => {
    onPlayStateChange?.(isPlaying, isReverse);
  }, [isPlaying, isReverse, onPlayStateChange]);

  // Animation frame clock driving smooth 60 FPS playback
  const lastRafTimeRef = React.useRef<number>(performance.now());
  React.useEffect(() => {
    if (!isPlaying) return;

    let animId: number;
    lastRafTimeRef.current = performance.now();

    const frameLoop = (time: number) => {
      const deltaSec = (time - lastRafTimeRef.current) / 1000;
      lastRafTimeRef.current = time;

      const increment = deltaSec * 15 * speedMultiplier;

      setInternalSeconds((prev) => {
        let next: number;
        if (isReverse) {
          next = prev - increment;
          if (next <= 0) {
            if (isLooping) next = totalDurationSeconds;
            else {
              setIsPlaying(false);
              return 0;
            }
          }
        } else {
          next = prev + increment;
          if (next >= totalDurationSeconds) {
            if (isLooping) next = 0;
            else {
              setIsPlaying(false);
              return totalDurationSeconds;
            }
          }
        }
        return next;
      });

      animId = requestAnimationFrame(frameLoop);
    };

    animId = requestAnimationFrame(frameLoop);
    return () => cancelAnimationFrame(animId);
  }, [isPlaying, isReverse, speedMultiplier, isLooping, totalDurationSeconds]);

  // User playback actions
  const handleTogglePlay = (reverse: boolean = false) => {
    if (isPlaying && isReverse === reverse) {
      setIsPlaying(false);
    } else {
      setIsReverse(reverse);
      setIsPlaying(true);
    }
  };

  const handleSliderChange = (vals: number[]) => {
    setIsPlaying(false);
    const val = vals[0] ?? 0;
    setInternalSeconds(val);
  };

  const handleJumpToStart = () => {
    setIsPlaying(false);
    setInternalSeconds(0);
  };

  const handleJumpToCpa = () => {
    setIsPlaying(false);
    setInternalSeconds(totalDurationSeconds * 0.5);
  };

  const handleJumpToEnd = () => {
    setIsPlaying(false);
    setInternalSeconds(totalDurationSeconds);
  };

  const handleStep = (stepSeconds: number) => {
    setIsPlaying(false);
    setInternalSeconds((prev) =>
      Math.max(0, Math.min(totalDurationSeconds, prev + stepSeconds))
    );
  };

  // Formatted string representations
  const formattedUtc = currentDate.toISOString().replace(".000Z", " UTC").replace("T", " ");
  const elapsedHours = (progress * 12.0).toFixed(1);
  const remainingHours = ((1.0 - progress) * 12.0).toFixed(1);

  return (
    <div
      className={`rounded-xl border border-hairline-dark bg-brand-teal-deep/95 p-4 shadow-2xl backdrop-blur-md text-white transition-all ${className}`}
      data-testid="investigation-time-scrubber"
    >
      {/* 1. Header Strip: Live Status, UTC Timestamp & Paired Confidence */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline-dark pb-3">
        {/* Playback Mode & Status */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                isPlaying
                  ? "bg-brand-green animate-pulse"
                  : "bg-on-dark-muted"
              }`}
            />
            <span className="text-xs font-bold uppercase tracking-wider text-white">
              Investigation Replay (D4)
            </span>
          </div>

          <Badge
            variant={isPlaying ? (isReverse ? "orange" : "green") : "secondary"}
            className="text-[10px] font-mono uppercase"
          >
            {isPlaying
              ? isReverse
                ? "⏪ Reverse Convergence"
                : "⏩ Forward Dispersion"
              : "⏸ Paused"}
          </Badge>
        </div>

        {/* Current Replay Timestamp & Elapsed Offset */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 font-mono text-sm font-semibold text-brand-green">
            <Clock className="h-4 w-4 text-brand-green" />
            <span>{formattedUtc}</span>
          </div>

          <div className="flex items-center gap-1.5 font-mono text-xs text-on-dark-muted">
            <span>+{elapsedHours}h from release</span>
            <span className="text-hairline-dark">|</span>
            <span>-{remainingHours}h to observation</span>
          </div>
        </div>

        {/* Rule 1 Paired Confidence & Live Top Attributed Candidate */}
        <div className="flex items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-1.5 rounded-lg border border-hairline-dark bg-white/5 px-2.5 py-1 font-mono text-xs text-brand-green">
                <ShieldCheck className="h-3.5 w-3.5 text-brand-green" />
                <span>Confidence: {topCandidate.confidencePct.toFixed(1)}%</span>
              </div>
            </TooltipTrigger>
            <TooltipContent>
              Constitutional Rule 1: Mandatory paired confidence assessment for active state
            </TooltipContent>
          </Tooltip>

          <Badge variant="green" className="text-xs font-mono">
            Rank 1: {topCandidate.name} (S: {topCandidate.score.toFixed(3)})
          </Badge>
        </div>
      </div>

      {/* 2. Timeline Scrubber Track with Milestone Annotations */}
      <div className="py-4 space-y-2">
        <Slider
          value={[currentSeconds]}
          min={0}
          max={totalDurationSeconds}
          step={1}
          onValueChange={handleSliderChange}
          className="cursor-pointer"
        />

        {/* Milestone Labels Along Track */}
        <div className="relative flex justify-between font-mono text-[10px] text-on-dark-muted px-1">
          {/* Release Window Marker (t_0) */}
          <button
            type="button"
            onClick={handleJumpToStart}
            className="text-left hover:text-brand-green transition-colors"
            title="Jump to Estimated Release Window"
          >
            <div className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-orange" />
              <span className="font-semibold text-white">t₀ Release Window</span>
            </div>
            <span>15:42:00 UTC (Origin)</span>
          </button>

          {/* CPA Crossing Marker (t_cpa) */}
          <button
            type="button"
            onClick={handleJumpToCpa}
            className="text-center hover:text-brand-green transition-colors"
            title="Jump to MT PACIFIC TRADER CPA Crossing"
          >
            <div className="flex items-center justify-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-brand-green" />
              <span className="font-semibold text-white">CPA Intersection (t_cpa)</span>
            </div>
            <span>21:42:00 UTC (Δ = 0.42 NM)</span>
          </button>

          {/* Observation Marker (t_obs) */}
          <button
            type="button"
            onClick={handleJumpToEnd}
            className="text-right hover:text-brand-green transition-colors"
            title="Jump to Sentinel-1A SAR Detection"
          >
            <div className="flex items-center justify-end gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-brand-green" />
              <span className="font-semibold text-white">t_obs SAR Observation</span>
            </div>
            <span>03:42:00 UTC (Copernicus)</span>
          </button>
        </div>
      </div>

      {/* 3. Playback Transport Controls & Speed Selector */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-hairline-dark">
        {/* Transport Action Buttons */}
        <div className="flex items-center gap-1.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="secondary"
                size="icon"
                onClick={handleJumpToStart}
                className="h-8 w-8 bg-brand-teal-deep border-hairline-dark text-on-dark-muted hover:text-white"
              >
                <SkipBack className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Jump to Spill Release Origin (t₀)</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="secondary"
                size="icon"
                onClick={() => handleStep(-90)} // -15 minutes in simulation units
                className="h-8 w-8 bg-brand-teal-deep border-hairline-dark text-on-dark-muted hover:text-white"
              >
                <Rewind className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Step -15 Minutes</TooltipContent>
          </Tooltip>

          {/* Reverse Play (Reverse Convergence, PRD US-14) */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={isPlaying && isReverse ? "default" : "secondary"}
                size="sm"
                onClick={() => handleTogglePlay(true)}
                className={`h-8 gap-1.5 text-xs font-medium ${
                  isPlaying && isReverse
                    ? "bg-accent-orange hover:bg-accent-orange/90 text-white"
                    : "bg-brand-teal-deep border-hairline-dark text-on-dark-muted hover:text-white"
                }`}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                <span>Reverse Play</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Animate reverse particle convergence from slick to origin envelope (PRD US-14)
            </TooltipContent>
          </Tooltip>

          {/* Forward Play / Pause Toggle */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={isPlaying && !isReverse ? "default" : "secondary"}
                size="sm"
                onClick={() => handleTogglePlay(false)}
                className={`h-8 gap-1.5 text-xs font-semibold ${
                  isPlaying && !isReverse
                    ? "bg-brand-green hover:bg-brand-green/90 text-brand-teal-deep"
                    : "bg-brand-teal-deep border-hairline-dark text-white hover:bg-white/5"
                }`}
              >
                {isPlaying && !isReverse ? (
                  <>
                    <Pause className="h-3.5 w-3.5" />
                    <span>Pause</span>
                  </>
                ) : (
                  <>
                    <Play className="h-3.5 w-3.5 fill-current" />
                    <span>Play</span>
                  </>
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>Play forward dispersion from origin to slick</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="secondary"
                size="icon"
                onClick={() => handleStep(90)} // +15 minutes
                className="h-8 w-8 bg-brand-teal-deep border-hairline-dark text-on-dark-muted hover:text-white"
              >
                <FastForward className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Step +15 Minutes</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="secondary"
                size="icon"
                onClick={handleJumpToEnd}
                className="h-8 w-8 bg-brand-teal-deep border-hairline-dark text-on-dark-muted hover:text-white"
              >
                <SkipForward className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Jump to SAR Observation (t_obs)</TooltipContent>
          </Tooltip>
        </div>

        {/* Speed Multipliers & Loop Toggle */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-medium text-on-dark-muted">Speed:</span>
          <div className="flex items-center rounded-lg border border-hairline-dark bg-brand-teal-deep p-0.5">
            {[1, 5, 10, 30].map((spd) => (
              <button
                key={spd}
                type="button"
                onClick={() => setSpeedMultiplier(spd)}
                className={`rounded-md px-2 py-0.5 font-mono text-xs transition-colors ${
                  speedMultiplier === spd
                    ? "bg-brand-green font-bold text-brand-teal-deep shadow"
                    : "text-on-dark-muted hover:text-white"
                }`}
              >
                {spd}×
              </button>
            ))}
          </div>

          {/* Loop Toggle */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsLooping(!isLooping)}
                className={`h-8 w-8 ${
                  isLooping ? "text-brand-green" : "text-on-dark-muted"
                }`}
              >
                <Repeat className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Loop Playback: {isLooping ? "On" : "Off"}</TooltipContent>
          </Tooltip>
        </div>

        {/* Dynamic Telemetry & deck.gl Link Badge */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 font-mono text-xs text-on-dark-muted">
            <Activity className="h-3.5 w-3.5 text-brand-green" />
            <span>deck.gl 10k Particles Synced</span>
          </div>

          <Badge variant="outline" className="font-mono text-xs">
            Progress: {(progress * 100).toFixed(1)}%
          </Badge>
        </div>
      </div>
    </div>
  );
}

export default TimeScrubber;
