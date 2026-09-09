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
  /** External play state control */
  isPlaying?: boolean;
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
  isPlaying: externalIsPlaying,
  onTimeChange,
  onRankingsChange,
  onPlayStateChange,
  className = "",
}: TimeScrubberProps) {
  // ── Stable refs for parent callbacks (prevent render-loop triggers) ──
  const onTimeChangeRef = React.useRef(onTimeChange);
  React.useEffect(() => { onTimeChangeRef.current = onTimeChange; });
  const onRankingsChangeRef = React.useRef(onRankingsChange);
  React.useEffect(() => { onRankingsChangeRef.current = onRankingsChange; });
  const onPlayStateChangeRef = React.useRef(onPlayStateChange);
  React.useEffect(() => { onPlayStateChangeRef.current = onPlayStateChange; });

  // ── Core time state (React-managed for rendering) ──
  const [displaySeconds, setDisplaySeconds] = React.useState<number>(externalTime ?? 540);

  // ── Playback engine state ──
  const [isPlaying, setIsPlaying] = React.useState<boolean>(externalIsPlaying ?? false);
  const [isReverse, setIsReverse] = React.useState<boolean>(false);
  const [speedMultiplier, setSpeedMultiplier] = React.useState<number>(5);
  const [isLooping, setIsLooping] = React.useState<boolean>(true);

  // ── Refs for animation loop (no React re-renders) ──
  const timeRef = React.useRef<number>(externalTime ?? 540);
  const isPlayingRef = React.useRef<boolean>(externalIsPlaying ?? false);
  const isReverseRef = React.useRef<boolean>(false);
  const speedRef = React.useRef<number>(5);
  const isLoopingRef = React.useRef<boolean>(true);
  const lastRafTimeRef = React.useRef<number>(0);
  const animIdRef = React.useRef<number>(0);
  const lastDisplayUpdateRef = React.useRef<number>(0);

  // Keep refs in sync with React state (one-way: React → ref)
  React.useEffect(() => { isPlayingRef.current = isPlaying; }, [isPlaying]);
  React.useEffect(() => { isReverseRef.current = isReverse; }, [isReverse]);
  React.useEffect(() => { speedRef.current = speedMultiplier; }, [speedMultiplier]);
  React.useEffect(() => { isLoopingRef.current = isLooping; }, [isLooping]);

  // ── Sync external play state from parent ──
  React.useEffect(() => {
    if (externalIsPlaying !== undefined && externalIsPlaying !== isPlayingRef.current) {
      isPlayingRef.current = externalIsPlaying;
      setIsPlaying(externalIsPlaying);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalIsPlaying]);

  // ── Sync external time from parent (only on significant jumps) ──
  const lastExternalTimeRef = React.useRef<number | undefined>(externalTime);
  React.useEffect(() => {
    if (externalTime !== undefined && externalTime !== lastExternalTimeRef.current) {
      const diff = Math.abs(timeRef.current - externalTime);
      if (diff > 2) {
        // Parent jumped significantly — sync
        timeRef.current = externalTime;
        setDisplaySeconds(externalTime);
      }
      lastExternalTimeRef.current = externalTime;
    }
  }, [externalTime]);

  // ── Time calculations ──
  const startDate = React.useMemo(() => new Date(startTimestamp), [startTimestamp]);
  const endDate = React.useMemo(() => new Date(endTimestamp), [endTimestamp]);
  const totalMs = React.useMemo(() => endDate.getTime() - startDate.getTime(), [startDate, endDate]);

  const currentSeconds = displaySeconds;
  const progress = Math.min(1, Math.max(0, currentSeconds / totalDurationSeconds));
  const currentDate = React.useMemo(
    () => new Date(startDate.getTime() + progress * totalMs),
    [startDate, progress, totalMs]
  );

  // ── Helper: emit discrete updates on user actions ──
  const emitDiscreteUpdate = React.useCallback((sec: number) => {
    const prog = Math.min(1, Math.max(0, sec / totalDurationSeconds));
    const curDate = new Date(startDate.getTime() + prog * totalMs);
    onTimeChangeRef.current?.(sec, prog, curDate);
    onRankingsChangeRef.current?.(computeDynamicRankings(prog));
  }, [totalDurationSeconds, startDate, totalMs]);

  // Dynamic evolving rankings at current simulation step
  const currentRankings = React.useMemo(() => computeDynamicRankings(progress), [progress]);
  const topCandidate = currentRankings[0];

  // ── Core Animation Loop (runs entirely via refs, no React state in hot path) ──
  React.useEffect(() => {
    // Single persistent RAF loop — starts on mount, cleaned up on unmount
    const frameLoop = (time: number) => {
      if (isPlayingRef.current) {
        const deltaSec = lastRafTimeRef.current > 0 
          ? Math.min((time - lastRafTimeRef.current) / 1000, 0.1) // cap at 100ms to prevent jumps
          : 0;
        lastRafTimeRef.current = time;

        const increment = deltaSec * 15 * speedRef.current;
        let next: number;

        if (isReverseRef.current) {
          next = timeRef.current - increment;
          if (next <= 0) {
            if (isLoopingRef.current) { next = totalDurationSeconds; }
            else {
              next = 0;
              isPlayingRef.current = false;
              setIsPlaying(false);
              onPlayStateChangeRef.current?.(false, true);
            }
          }
        } else {
          next = timeRef.current + increment;
          if (next >= totalDurationSeconds) {
            if (isLoopingRef.current) { next = 0; }
            else {
              next = totalDurationSeconds;
              isPlayingRef.current = false;
              setIsPlaying(false);
              onPlayStateChangeRef.current?.(false, false);
            }
          }
        }

        timeRef.current = next;

        // Throttle React state updates to ~30fps to avoid render storms
        if (time - lastDisplayUpdateRef.current > 33) {
          lastDisplayUpdateRef.current = time;
          setDisplaySeconds(next);

          // Notify parent
          const prog = Math.min(1, Math.max(0, next / totalDurationSeconds));
          const curDate = new Date(startDate.getTime() + prog * totalMs);
          onTimeChangeRef.current?.(next, prog, curDate);
          onRankingsChangeRef.current?.(computeDynamicRankings(prog));
        }
      } else {
        lastRafTimeRef.current = 0; // Reset so next play doesn't get a huge delta
      }

      animIdRef.current = requestAnimationFrame(frameLoop);
    };

    animIdRef.current = requestAnimationFrame(frameLoop);
    return () => cancelAnimationFrame(animIdRef.current);
    // Intentionally stable — all values are read from refs
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totalDurationSeconds]);

  // User playback actions
  const handleTogglePlay = (reverse: boolean = false) => {
    const nextPlaying = isPlaying && isReverse === reverse ? false : true;
    if (isPlaying && isReverse === reverse) {
      isPlayingRef.current = false;
      setIsPlaying(false);
    } else {
      isReverseRef.current = reverse;
      setIsReverse(reverse);
      isPlayingRef.current = true;
      setIsPlaying(true);
    }
    onPlayStateChangeRef.current?.(nextPlaying, reverse);
  };

  const handleSliderChange = (vals: number[]) => {
    isPlayingRef.current = false;
    setIsPlaying(false);
    onPlayStateChangeRef.current?.(false, isReverse);
    const val = vals[0] ?? 0;
    timeRef.current = val;
    setDisplaySeconds(val);
    emitDiscreteUpdate(val);
  };

  const handleJumpToStart = () => {
    isPlayingRef.current = false;
    setIsPlaying(false);
    onPlayStateChangeRef.current?.(false, isReverse);
    timeRef.current = 0;
    setDisplaySeconds(0);
    emitDiscreteUpdate(0);
  };

  const handleJumpToCpa = () => {
    isPlayingRef.current = false;
    setIsPlaying(false);
    onPlayStateChangeRef.current?.(false, isReverse);
    const cpaSec = totalDurationSeconds * 0.5;
    timeRef.current = cpaSec;
    setDisplaySeconds(cpaSec);
    emitDiscreteUpdate(cpaSec);
  };

  const handleJumpToEnd = () => {
    isPlayingRef.current = false;
    setIsPlaying(false);
    onPlayStateChangeRef.current?.(false, isReverse);
    timeRef.current = totalDurationSeconds;
    setDisplaySeconds(totalDurationSeconds);
    emitDiscreteUpdate(totalDurationSeconds);
  };

  const handleStep = (stepSeconds: number) => {
    isPlayingRef.current = false;
    setIsPlaying(false);
    onPlayStateChangeRef.current?.(false, isReverse);
    const next = Math.max(0, Math.min(totalDurationSeconds, timeRef.current + stepSeconds));
    timeRef.current = next;
    setDisplaySeconds(next);
    emitDiscreteUpdate(next);
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
