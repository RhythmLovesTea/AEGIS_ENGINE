import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-3.5 [&_svg]:shrink-0 rounded-sm",
  {
    variants: {
      variant: {
        default:
          "border border-emerald-500/50 bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 hover:border-emerald-400 rounded-sm",
        secondary:
          "border border-slate-700 bg-slate-800/80 text-slate-200 hover:border-slate-500 hover:bg-slate-800 rounded-sm",
        destructive:
          "border border-red-500/40 bg-red-500/20 text-red-300 hover:bg-red-500/30 rounded-sm",
        outline:
          "border border-[#1F2937] bg-transparent text-slate-300 hover:bg-slate-800/60 hover:text-white rounded-sm",
        ghost:
          "hover:bg-slate-800/80 text-slate-300 hover:text-white rounded-sm",
        link:
          "text-emerald-400 underline-offset-4 hover:underline",
        industrialGhost:
          "border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 text-xs px-3 py-1.5 rounded-sm",
        pill:
          "border border-emerald-500/50 bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 rounded-sm px-4 py-1.5",
      },
      size: {
        default: "h-8 px-3 py-1.5",
        sm: "h-7 px-2.5 text-xs",
        lg: "h-9 px-4 text-sm",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
