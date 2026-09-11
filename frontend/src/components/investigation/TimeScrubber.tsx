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
      className={`rounded-sm border border-[#1F2937] bg-[#111720] p-4 text-slate-100 shadow-2xl transition-all ${className}`}
      data-testid="investigation-time-scrubber"
    >
      {/* 1. Header Strip: Terminal Status, UTC Timestamp & Structured Suspect Telemetry */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#1F2937] pb-3 font-mono">
        {/* Terminal Status Line */}
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              isPlaying ? "bg-emerald-400 animate-ping" : "bg-slate-600"
            }`}
          />
          <span className="text-xs font-mono font-bold text-slate-300 tracking-wide">
            ● REPLAY MODE: {isReverse ? "REVERSE CONVERGENCE" : "FORWARD DISPERSION"} [
            {isPlaying ? "RUNNING" : "PAUSED"}]
          </span>
        </div>

        {/* Current Replay Timestamp & Elapsed Offset */}
        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5 font-semibold text-emerald-400">
            <Clock className="h-3.5 w-3.5 text-emerald-400" />
            <span className="tabular-nums">{formattedUtc}</span>
          </div>
          <div className="flex items-center gap-1.5 text-slate-400 tabular-nums text-[11px]">
            <span>+{elapsedHours}h from release</span>
            <span className="text-slate-700">│</span>
            <span>-{remainingHours}h to observation</span>
          </div>
        </div>

        {/* Structured Suspect Telemetry Readout */}
        <div className="rounded-sm border border-slate-800 bg-slate-900/80 px-2.5 py-1 text-[11px] text-slate-300 tabular-nums">
          <span>SUSPECT: {topCandidate.name}</span>
          <span className="text-slate-700 mx-1.5">│</span>
          <span>ANOMALY INDEX: {topCandidate.score.toFixed(3)}</span>
          <span className="text-slate-700 mx-1.5">│</span>
          <span className="text-emerald-400 font-semibold">
            P(CULPRIT): {topCandidate.confidencePct.toFixed(1)}% [BAYESIAN]
          </span>
        </div>
      </div>

      {/* 2. Timeline Scrubber: Precision Ruler Track with Vertical Tick Marks & Needles */}
      <div className="py-4 space-y-2">
        <div className="relative">
          <Slider
            value={[currentSeconds]}
            min={0}
            max={totalDurationSeconds}
            step={1}
            onValueChange={handleSliderChange}
            className="cursor-pointer"
          />

          {/* Precision Ruler 1-Hour UTC Interval Tick Marks */}
          <div className="pointer-events-none absolute inset-x-0 top-3 flex justify-between px-1">
            {Array.from({ length: 13 }).map((_, i) => (
              <div key={i} className="flex flex-col items-center">
                <div
                  className={`w-[1px] ${
                    i % 3 === 0 ? "h-2.5 bg-slate-500" : "h-1.5 bg-slate-700"
                  }`}
                />
                {i % 3 === 0 && (
                  <span className="text-[9px] font-mono text-slate-500 tabular-nums mt-0.5">
                    {String(15 + i).padStart(2, "0")}:00
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Milestone Vertical Tags with Precise UTC Offsets */}
        <div className="relative flex justify-between font-mono text-[10px] text-slate-400 px-1 pt-3">
          {/* Release Window Marker (t_0) */}
          <button
            type="button"
            onClick={handleJumpToStart}
            className="flex flex-col items-start hover:text-emerald-400 transition-colors text-left"
            title="Jump to Estimated Release Window"
          >
            <span className="border-l-2 border-amber-500 pl-1.5 font-bold text-slate-200">
              t₀ RELEASE WINDOW
            </span>
            <span className="pl-2 text-slate-400 tabular-nums">
              15:42:00 UTC [Δt: -12.0h]
            </span>
          </button>

          {/* CPA Crossing Marker (t_cpa) */}
          <button
            type="button"
            onClick={handleJumpToCpa}
            className="flex flex-col items-center hover:text-emerald-400 transition-colors text-center"
            title="Jump to MT PACIFIC TRADER CPA Crossing"
          >
            <span className="border-t-2 border-sky-400 px-1.5 font-bold text-slate-200">
              CPA INTERSECTION
            </span>
            <span className="text-slate-400 tabular-nums">
              21:42:00 UTC [Δt: -6.0h]
            </span>
          </button>

          {/* Observation Marker (t_obs) */}
          <button
            type="button"
            onClick={handleJumpToEnd}
            className="flex flex-col items-end hover:text-emerald-400 transition-colors text-right"
            title="Jump to Sentinel-1A SAR Detection"
          >
            <span className="border-r-2 border-emerald-400 pr-1.5 font-bold text-slate-200">
              t_obs SAR DETECT
            </span>
            <span className="pr-2 text-slate-400 tabular-nums">
              03:42:00 UTC [Δt: 0.0h]
            </span>
          </button>
        </div>
      </div>

      {/* 3. Playback Transport Controls & Speed Selector */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-[#1F2937]">
        {/* Transport Action Buttons */}
        <div className="flex items-center gap-1.5 font-mono">
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={handleJumpToStart}
                className="h-7 w-7 rounded-sm border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white hover:border-slate-500 flex items-center justify-center transition-colors"
              >
                <SkipBack className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Jump to Spill Release Origin (t₀)</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => handleStep(-90)} // -15 minutes
                className="h-7 w-7 rounded-sm border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white hover:border-slate-500 flex items-center justify-center transition-colors"
              >
                <Rewind className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Step -15 Minutes</TooltipContent>
          </Tooltip>

          {/* Reverse Play */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => handleTogglePlay(true)}
                className={`h-7 px-2.5 gap-1.5 rounded-sm border text-xs font-mono font-medium flex items-center transition-colors ${
                  isPlaying && isReverse
                    ? "border-amber-500/60 bg-amber-500/20 text-amber-300"
                    : "border-slate-700 bg-slate-800/80 text-slate-300 hover:border-slate-500 hover:text-white"
                }`}
              >
                <RotateCcw className="h-3 w-3" />
                <span>Reverse Play</span>
              </button>
            </TooltipTrigger>
            <TooltipContent>
              Animate reverse particle convergence from slick to origin envelope (PRD US-14)
            </TooltipContent>
          </Tooltip>

          {/* Forward Play / Pause Toggle */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => handleTogglePlay(false)}
                className={`h-7 px-3 gap-1.5 rounded-sm border text-xs font-mono font-medium flex items-center transition-colors ${
                  isPlaying && !isReverse
                    ? "border-emerald-500/60 bg-emerald-500/20 text-emerald-300"
                    : "border-slate-700 bg-slate-800/80 text-slate-200 hover:border-slate-500 hover:text-white"
                }`}
              >
                {isPlaying && !isReverse ? (
                  <>
                    <Pause className="h-3 w-3" />
                    <span>Pause</span>
                  </>
                ) : (
                  <>
                    <Play className="h-3 w-3 fill-current" />
                    <span>Play</span>
                  </>
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent>Play forward dispersion from origin to slick</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => handleStep(90)} // +15 minutes
                className="h-7 w-7 rounded-sm border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white hover:border-slate-500 flex items-center justify-center transition-colors"
              >
                <FastForward className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Step +15 Minutes</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={handleJumpToEnd}
                className="h-7 w-7 rounded-sm border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white hover:border-slate-500 flex items-center justify-center transition-colors"
              >
                <SkipForward className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Jump to SAR Observation (t_obs)</TooltipContent>
          </Tooltip>
        </div>

        {/* Speed Multipliers & Loop Toggle */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-slate-400">Speed:</span>
          <div className="flex items-center rounded-sm border border-slate-800 bg-slate-900/90 p-0.5">
            {[1, 5, 10, 30].map((spd) => (
              <button
                key={spd}
                type="button"
                onClick={() => setSpeedMultiplier(spd)}
                className={`rounded-sm px-2 py-0.5 font-mono text-xs transition-colors ${
                  speedMultiplier === spd
                    ? "bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/40"
                    : "text-slate-400 hover:text-white border border-transparent"
                }`}
              >
                {spd}×
              </button>
            ))}
          </div>

          {/* Loop Toggle */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => setIsLooping(!isLooping)}
                className={`h-7 w-7 rounded-sm border border-slate-800 flex items-center justify-center transition-colors ${
                  isLooping ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/40" : "text-slate-400 hover:text-white"
                }`}
              >
                <Repeat className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Loop Playback: {isLooping ? "On" : "Off"}</TooltipContent>
          </Tooltip>
        </div>

        {/* Dynamic Telemetry & deck.gl Link Badge */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 font-mono text-xs text-slate-400 tabular-nums">
            <Activity className="h-3.5 w-3.5 text-emerald-400" />
            <span>deck.gl 10k Particles Synced</span>
          </div>

          <span className="rounded-sm border border-slate-800 bg-slate-900/60 px-2 py-0.5 font-mono text-xs text-slate-300 tabular-nums">
            Progress: {(progress * 100).toFixed(1)}%
          </span>
        </div>
      </div>
    </div>
  );
}

export default TimeScrubber;
