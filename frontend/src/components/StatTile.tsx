import { cva, type VariantProps } from "class-variance-authority";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Número-herói + rótulo + sublabel.
 * `size="hero"` é o único número ≥48px da view (regra dataviz: um herói por tela).
 * `tone="accent"` pinta o número em âmbar (acento escasso, reservado ao destaque).
 */
const value = cva("font-semibold leading-none tracking-tight", {
  variants: {
    size: {
      hero: "text-5xl md:text-6xl",
      lg: "text-3xl",
      md: "text-2xl",
    },
    tone: {
      default: "text-foreground",
      onHero: "text-white",
      accent: "text-gold-500 dark:text-gold-400",
    },
  },
  defaultVariants: { size: "md", tone: "default" },
});

export interface StatTileProps extends VariantProps<typeof value> {
  label?: string;
  value: string;
  sublabel?: ReactNode;
  className?: string;
}

export function StatTile({
  size,
  tone,
  label,
  value: valueText,
  sublabel,
  className,
}: StatTileProps) {
  const onHero = tone === "onHero";
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {label && (
        <span
          className={cn(
            "text-xs font-medium uppercase tracking-wider",
            onHero ? "text-teal-100/80" : "text-muted-foreground",
          )}
        >
          {label}
        </span>
      )}
      <span className={value({ size, tone })}>{valueText}</span>
      {sublabel && (
        <span
          className={cn(
            "text-xs",
            onHero ? "text-teal-100/70" : "text-muted-foreground",
          )}
        >
          {sublabel}
        </span>
      )}
    </div>
  );
}
