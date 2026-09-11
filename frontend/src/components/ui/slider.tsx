"use client";

import * as React from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";

import { cn } from "@/lib/utils";

const Slider = React.forwardRef<
  React.ElementRef<typeof SliderPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SliderPrimitive.Root
    ref={ref}
    className={cn(
      "relative flex w-full touch-none select-none items-center py-2",
      className
    )}
    {...props}
  >
    {/* Precision Ruler Track */}
    <SliderPrimitive.Track className="relative h-[2px] w-full grow bg-slate-800">
      <SliderPrimitive.Range className="absolute h-full bg-emerald-500/80" />
    </SliderPrimitive.Track>

    {/* Tactical Vertical Needle Thumb with Inverted Triangle Marker */}
    <SliderPrimitive.Thumb className="relative -top-2.5 flex flex-col items-center justify-center focus:outline-none cursor-ew-resize select-none">
      <span className="text-[10px] text-cyan-400 font-mono leading-none -mb-1 drop-shadow-[0_0_4px_rgba(56,189,248,0.8)]">
        ▼
      </span>
      <div className="w-[2px] h-6 bg-cyan-300 shadow-[0_0_6px_rgba(56,189,248,0.9)]" />
    </SliderPrimitive.Thumb>
  </SliderPrimitive.Root>
));
Slider.displayName = SliderPrimitive.Root.displayName;

export { Slider };
