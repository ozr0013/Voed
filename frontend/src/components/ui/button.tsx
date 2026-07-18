"use client";

import * as React from "react";
import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-none border-[3px] text-center font-bold tracking-[-0.015em] transition-all duration-150 ease-in-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 select-none cursor-pointer",
  {
    variants: {
      variant: {
        default:
          "bg-accent border-white text-white shadow-[3px_3px_0px_0px_rgba(255,255,255,0.35)] hover:translate-x-[1.5px] hover:translate-y-[1.5px] hover:shadow-[1.5px_1.5px_0px_0px_rgba(255,255,255,0.35)] active:translate-x-[3px] active:translate-y-[3px] active:shadow-[0px_0px_0px_0px_rgba(255,255,255,0.35)]",
        destructive:
          "bg-bad border-white text-white shadow-[3px_3px_0px_0px_rgba(255,255,255,0.35)] hover:translate-x-[1.5px] hover:translate-y-[1.5px] hover:shadow-[1.5px_1.5px_0px_0px_rgba(255,255,255,0.35)] active:translate-x-[3px] active:translate-y-[3px] active:shadow-[0px_0px_0px_0px_rgba(255,255,255,0.35)]",
        outline:
          "bg-transparent border-white text-white shadow-[3px_3px_0px_0px_rgba(255,255,255,0.35)] hover:translate-x-[1.5px] hover:translate-y-[1.5px] hover:shadow-[1.5px_1.5px_0px_0px_rgba(255,255,255,0.35)] active:translate-x-[3px] active:translate-y-[3px] active:shadow-[0px_0px_0px_0px_rgba(255,255,255,0.35)]",
        secondary:
          "bg-panel border-edge text-white/90 shadow-[3px_3px_0px_0px_rgba(255,255,255,0.15)] hover:translate-x-[1.5px] hover:translate-y-[1.5px] hover:shadow-[1.5px_1.5px_0px_0px_rgba(255,255,255,0.15)] hover:border-white active:translate-x-[3px] active:translate-y-[3px] active:shadow-[0px_0px_0px_0px_rgba(255,255,255,0.15)]",
        ghost:
          "bg-transparent border-transparent text-white/80 hover:bg-panel hover:text-white hover:border-edge hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[1px_1px_0px_0px_rgba(255,255,255,0.1)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-[0px_0px_0px_0px_rgba(255,255,255,0.1)]",
        link:
          "border-none bg-transparent text-accent underline-offset-4 hover:underline hover:text-accent/90",
      },
      size: {
        default: "h-9 px-6 py-1.5 text-sm",
        xs: "h-7 px-4 py-1 text-xs",
        sm: "h-8 px-5 py-1.5 text-xs",
        lg: "h-11 px-8 py-2 text-base",
        icon: "h-9 w-9 p-0",
        "icon-xs": "h-7 w-7 p-0",
        "icon-sm": "h-8 w-8 p-0",
        "icon-lg": "h-11 w-11 p-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

interface ButtonProps
  extends React.ComponentPropsWithoutRef<typeof ButtonPrimitive>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <ButtonPrimitive
        ref={ref}
        className={cn(buttonVariants({ variant, size, className }))}
        {...props}
      />
    );
  }
);

Button.displayName = "Button";

export { Button, buttonVariants };
