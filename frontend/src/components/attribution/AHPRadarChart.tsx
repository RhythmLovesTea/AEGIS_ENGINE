"use client";

import * as React from "react";
import type { SubScores } from "@/types";

export interface AHPRadarChartProps {
  subScores: SubScores;
  weights?: Record<string, number>;
  benchmarks?: Record<string, number>;
  vesselName?: string;
  size?: number;
  className?: string;
}

interface AxisConfig {
  key: keyof SubScores;
  label: string;
  shortLabel: string;
  defaultWeight: number;
  defaultBenchmark: number;
}

const AXIS_CONFIGS: AxisConfig[] = [
  {
    key: "spatial",
    label: "Spatial Proximity",
    shortLabel: "Spatial",
    defaultWeight: 0.30,
    defaultBenchmark: 25.0,
  },
  {
    key: "temporal",
    label: "Temporal Proximity",
    shortLabel: "Temporal",
    defaultWeight: 0.25,
    defaultBenchmark: 20.0,
  },
  {
    key: "kinematic",
    label: "Kinematic Alignment",
    shortLabel: "Kinematic",
    defaultWeight: 0.15,
    defaultBenchmark: 30.0,
  },
  {
    key: "anomaly",
    label: "Behavioral Anomaly",
    shortLabel: "Anomaly",
    defaultWeight: 0.20,
    defaultBenchmark: 10.0,
  },
  {
    key: "type",
    label: "Vessel Type Prior",
    shortLabel: "Type Prior",
    defaultWeight: 0.10,
    defaultBenchmark: 40.0,
  },
];

const GRID_LEVELS = [0.2, 0.4, 0.6, 0.8, 1.0];

export function AHPRadarChart({
  subScores,
  weights,
  benchmarks,
  vesselName = "Candidate Suspect",
  size = 320,
  className = "",
}: AHPRadarChartProps) {
  const [hoveredAxis, setHoveredAxis] = React.useState<string | null>(null);

  const cx = size / 2;
  const cy = size / 2;
  const radius = Math.min(cx, cy) - 52;
  const numAxes = AXIS_CONFIGS.length;
  const angleStep = (Math.PI * 2) / numAxes;

  // Compute coordinate for an axis angle and radius value
  const getCoordinates = React.useCallback(
    (axisIndex: number, value: number, maxRadius: number) => {
      // Start from top (-PI / 2) and rotate clockwise
      const angle = -Math.PI / 2 + axisIndex * angleStep;
      const r = (Math.max(0, Math.min(100, value)) / 100) * maxRadius;
      return {
        x: cx + r * Math.cos(angle),
        y: cy + r * Math.sin(angle),
        angle,
      };
    },
    [cx, cy, angleStep]
  );

  const gridPolygons = React.useMemo(() => {
    return GRID_LEVELS.map((level) => {
      const points = AXIS_CONFIGS.map((_, i) => {
        const coords = getCoordinates(i, level * 100, radius);
        return `${coords.x.toFixed(1)},${coords.y.toFixed(1)}`;
      }).join(" ");
      return { level, points };
    });
  }, [radius, getCoordinates]);

  // Candidate evaluation polygon points
  const candidatePoints = React.useMemo(() => {
    return AXIS_CONFIGS.map((axis, i) => {
      const val = typeof subScores[axis.key] === "number" ? (subScores[axis.key] as number) : 0;
      const coords = getCoordinates(i, val, radius);
      return `${coords.x.toFixed(1)},${coords.y.toFixed(1)}`;
    }).join(" ");
  }, [subScores, radius, getCoordinates]);

  // Regional baseline polygon points
  const benchmarkPoints = React.useMemo(() => {
    return AXIS_CONFIGS.map((axis, i) => {
      const val = benchmarks?.[axis.key] ?? axis.defaultBenchmark;
      const coords = getCoordinates(i, val, radius);
      return `${coords.x.toFixed(1)},${coords.y.toFixed(1)}`;
    }).join(" ");
  }, [benchmarks, radius, getCoordinates]);

  return (
    <div className={`flex flex-col items-center select-none ${className}`}>
      <div className="relative">
        <svg
          width={size}
          height={size}
          className="overflow-visible"
          aria-label="5-Axis AHP Explainability Radar Chart"
        >
          <defs>
            {/* Candidate area gradient */}
            <radialGradient id="candidateGradient" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#00ed64" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#00684a" stopOpacity="0.15" />
            </radialGradient>
            {/* Benchmark area gradient */}
            <radialGradient id="benchmarkGradient" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#3d4f5b" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#1c2d38" stopOpacity="0.05" />
            </radialGradient>
          </defs>

          {/* 1. Background Grid Rings */}
          {gridPolygons.map(({ level, points }) => (
            <polygon
              key={level}
              points={points}
              fill="transparent"
              stroke="#1c2d38"
              strokeWidth="1"
              strokeDasharray={level === 1.0 ? undefined : "2 2"}
            />
          ))}

          {/* Grid Scale Level Labels (on top vertical axis) */}
          {GRID_LEVELS.map((lvl) => {
            const yPos = cy - radius * lvl;
            return (
              <text
                key={lvl}
                x={cx + 4}
                y={yPos + 3}
                fill="#5c6c7a"
                fontSize="9"
                fontFamily="monospace"
              >
                {Math.round(lvl * 100)}
              </text>
            );
          })}

          {/* 2. Radial Axis Lines */}
          {AXIS_CONFIGS.map((axis, i) => {
            const endCoords = getCoordinates(i, 100, radius);
            const isHovered = hoveredAxis === axis.key;
            return (
              <line
                key={axis.key}
                x1={cx}
                y1={cy}
                x2={endCoords.x}
                y2={endCoords.y}
                stroke={isHovered ? "#00ed64" : "#1c2d38"}
                strokeWidth={isHovered ? "1.5" : "1"}
                className="transition-colors duration-200"
              />
            );
          })}

          {/* 3. Regional Fleet Baseline Polygon */}
          <polygon
            points={benchmarkPoints}
            fill="url(#benchmarkGradient)"
            stroke="#5c6c7a"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            className="transition-all duration-300"
          />

          {/* 4. Candidate Evaluation Polygon */}
          <polygon
            points={candidatePoints}
            fill="url(#candidateGradient)"
            stroke="#00ed64"
            strokeWidth="2.5"
            className="transition-all duration-300 drop-shadow-[0_0_8px_rgba(0,237,100,0.3)]"
          />

          {/* 5. Interactive Vertex Dots & Values */}
          {AXIS_CONFIGS.map((axis, i) => {
            const val =
              typeof subScores[axis.key] === "number"
                ? (subScores[axis.key] as number)
                : 0;
            const coords = getCoordinates(i, val, radius);
            const isHovered = hoveredAxis === axis.key;

            return (
              <g
                key={axis.key}
                className="cursor-pointer transition-transform"
                onMouseEnter={() => setHoveredAxis(axis.key)}
                onMouseLeave={() => setHoveredAxis(null)}
              >
                {/* Glowing Outer Ring */}
                <circle
                  cx={coords.x}
                  cy={coords.y}
                  r={isHovered ? 6 : 4}
                  fill="#00ed64"
                  stroke="#001e2b"
                  strokeWidth="2"
                  className="transition-all duration-200"
                />
              </g>
            );
          })}

          {/* 6. Axis Labels & Weights around perimeter */}
          {AXIS_CONFIGS.map((axis, i) => {
            const labelRadius = radius + 28;
            const coords = getCoordinates(i, 100, labelRadius);
            const val =
              typeof subScores[axis.key] === "number"
                ? (subScores[axis.key] as number)
                : 0;
            const weightPct = Math.round(
              (weights?.[axis.key] ?? axis.defaultWeight) * 100
            );
            const isHovered = hoveredAxis === axis.key;

            // Compute text anchor based on angle
            const angle = -Math.PI / 2 + i * angleStep;
            let textAnchor: "start" | "middle" | "end" = "middle";
            if (Math.cos(angle) > 0.3) {
              textAnchor = "start";
            } else if (Math.cos(angle) < -0.3) {
              textAnchor = "end";
            }

            return (
              <g
                key={axis.key}
                className="cursor-pointer"
                onMouseEnter={() => setHoveredAxis(axis.key)}
                onMouseLeave={() => setHoveredAxis(null)}
              >
                <text
                  x={coords.x}
                  y={coords.y - 4}
                  textAnchor={textAnchor}
                  fill={isHovered ? "#00ed64" : "#ffffff"}
                  fontSize="11"
                  fontWeight="600"
                  className="transition-colors duration-200"
                >
                  {axis.shortLabel}
                </text>
                <text
                  x={coords.x}
                  y={coords.y + 10}
                  textAnchor={textAnchor}
                  fill={isHovered ? "#00ed64" : "#a8b3bc"}
                  fontSize="10"
                  fontFamily="monospace"
                  className="transition-colors duration-200"
                >
                  {val.toFixed(1)} ({weightPct}%)
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Chart Legend */}
      <div className="mt-3 flex items-center justify-center gap-5 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-brand-green shadow-[0_0_6px_#00ed64]" />
          <span className="font-medium text-white">{vesselName}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-0.5 w-3 border-t-2 border-dashed border-steel" />
          <span className="text-on-dark-muted">Regional Fleet Baseline</span>
        </div>
      </div>
    </div>
  );
}

export default AHPRadarChart;
