import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-sm px-2 py-0.5 text-[11px] font-mono font-medium tracking-tight tabular-nums transition-colors focus:outline-none",
  {
    variants: {
      variant: {
        default:
          "border border-emerald-500/40 bg-emerald-500/15 text-emerald-300",
        green:
          "border border-emerald-500/40 bg-emerald-500/15 text-emerald-300",
        greenSoft:
          "border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded-sm",
        purple:
          "border border-purple-500/40 bg-purple-500/15 text-purple-300",
        orange:
          "border border-amber-500/40 bg-amber-500/15 text-amber-300",
        blue:
          "border border-sky-500/40 bg-sky-500/15 text-sky-300",
        secondary:
          "border border-slate-800 bg-slate-900/80 text-slate-300",
        destructive:
          "border border-red-500/40 bg-red-500/15 text-red-300",
        outline:
          "border border-slate-800 bg-slate-900/60 text-slate-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
