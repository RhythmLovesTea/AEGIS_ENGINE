import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-sm px-2 py-0.5 text-xs font-bold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "bg-brand-green text-brand-teal-deep hover:bg-brand-green/90",
        green:
          "bg-brand-green text-brand-teal-deep hover:bg-brand-green/90",
        greenSoft:
          "bg-brand-green-soft text-brand-green-dark rounded-full px-2.5 py-0.5",
        purple:
          "bg-accent-purple text-white hover:bg-accent-purple/90",
        orange:
          "bg-accent-orange text-white hover:bg-accent-orange/90",
        blue:
          "bg-accent-blue text-white hover:bg-accent-blue/90",
        secondary:
          "bg-hairline-dark text-on-dark hover:bg-hairline-dark/80",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline:
          "border border-hairline-dark text-on-dark",
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
