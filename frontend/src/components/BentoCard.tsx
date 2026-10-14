import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Tile do bento grid. As variantes `span`/`rows` controlam quantas colunas/linhas
 * o tile ocupa (o grid é responsivo, definido na página). `emphasis` muda o
 * acabamento: `hero` = superfície petróleo para o número-herói; `accent` = fino
 * realce âmbar; `plain` = card neutro padrão.
 */
const bentoCard = cva(
  "group relative flex flex-col overflow-hidden rounded-lg border p-5 transition-colors animate-fade-in",
  {
    variants: {
      emphasis: {
        plain: "border-border bg-card text-card-foreground shadow-sm",
        hero: "border-teal-700/60 bg-teal-800 text-teal-50 shadow-md dark:bg-teal-900",
        accent:
          "border-gold-500/40 bg-card text-card-foreground shadow-sm ring-1 ring-inset ring-gold-500/20",
      },
      span: {
        1: "md:col-span-1",
        2: "md:col-span-2",
        3: "md:col-span-3",
        4: "md:col-span-4",
      },
      rows: {
        1: "md:row-span-1",
        2: "md:row-span-2",
      },
    },
    defaultVariants: { emphasis: "plain", span: 1, rows: 1 },
  },
);

export interface BentoCardProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof bentoCard> {
  /** Rótulo curto no topo do tile (sentence case, sem dois-pontos). */
  label?: string;
  /** Conteúdo auxiliar à direita do rótulo (ex.: ícone, data). */
  headerRight?: ReactNode;
}

export function BentoCard({
  className,
  emphasis,
  span,
  rows,
  label,
  headerRight,
  children,
  ...props
}: BentoCardProps) {
  return (
    <section
      className={cn(bentoCard({ emphasis, span, rows }), className)}
      {...props}
    >
      {(label || headerRight) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          {label && (
            <h2
              className={cn(
                "text-xs font-medium uppercase tracking-wider",
                emphasis === "hero"
                  ? "text-teal-100/80"
                  : "text-muted-foreground",
              )}
            >
              {label}
            </h2>
          )}
          {headerRight && (
            <div className="shrink-0 text-xs text-muted-foreground">
              {headerRight}
            </div>
          )}
        </header>
      )}
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
    </section>
  );
}
