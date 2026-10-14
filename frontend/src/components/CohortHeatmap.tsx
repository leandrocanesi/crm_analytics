import { useState } from "react";

import type { Cohort, CohortPoint } from "@/lib/api";
import { formatMonthShort, formatNumber, formatPercent } from "@/lib/format";
import { retentionColor } from "@/lib/retentionScale";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

/**
 * Triângulo/heatmap de coortes de retenção.
 * Grid: linhas = cohort_month (ASC), colunas = months_since (0..N). A célula é
 * colorida por retention_rate numa rampa sequencial teal (mais escuro = maior
 * retenção; ver lib/retentionScale). Nº de colunas por linha é VARIÁVEL — cada
 * célula é posicionada por months_since, não por índice, então coortes tardias
 * deixam a direita VAZIA (right-censoring, intencional).
 *
 * Células cujo mês de atividade cai no mês-fronteira parcial (as_of) ganham
 * borda tracejada e marca "parcial" no tooltip — a taxa ~0 ali é artefato.
 */

interface HoverState {
  cohort: Cohort;
  point: CohortPoint;
  partial: boolean;
  x: number;
  y: number;
}

export function CohortHeatmap({
  cohorts,
  asOfDate,
}: {
  cohorts: Cohort[];
  asOfDate: string;
}) {
  const { theme } = useTheme();
  const [hover, setHover] = useState<HoverState | null>(null);

  const maxMonths = cohorts.reduce(
    (acc, c) =>
      c.points.reduce((m, p) => Math.max(m, p.months_since), acc),
    0,
  );
  const columns = Array.from({ length: maxMonths + 1 }, (_, i) => i);

  // "YYYY-MM" do mês-fronteira parcial (as_of). Atividade nesse mês é parcial.
  const partialMonth = asOfDate.slice(0, 7);

  return (
    <div className="relative">
      <div className="overflow-x-auto pb-1">
        <div
          role="group"
          aria-label="Retenção por coorte e meses desde a primeira compra"
          className="inline-grid gap-1 text-xs"
          style={{
            gridTemplateColumns: `minmax(6rem, auto) repeat(${columns.length}, minmax(2.6rem, 1fr))`,
          }}
          onMouseLeave={() => setHover(null)}
        >
          {/* Cabeçalho: canto + rótulos de months_since */}
          <div className="sticky left-0 z-10 bg-card px-1 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Coorte
          </div>
          {columns.map((m) => (
            <div
              key={`h-${m}`}
              className="px-1 py-1 text-center text-[10px] font-medium tabular-nums text-muted-foreground"
            >
              M{m}
            </div>
          ))}

          {/* Linhas por coorte */}
          {cohorts.map((cohort) => {
            const byMonth = new Map(
              cohort.points.map((p) => [p.months_since, p]),
            );
            return (
              <CohortRow
                key={cohort.cohort_month}
                cohort={cohort}
                columns={columns}
                byMonth={byMonth}
                partialMonth={partialMonth}
                theme={theme}
                onHover={setHover}
              />
            );
          })}
        </div>
      </div>

      {/* Legenda sequencial */}
      <HeatmapLegend theme={theme} />

      {/* Tooltip flutuante (segue o cursor) */}
      {hover && (
        <div
          className="pointer-events-none fixed z-50 rounded-md border border-border bg-popover px-3 py-2 text-xs shadow-md"
          style={{
            left: hover.x + 12,
            top: hover.y + 12,
            maxWidth: "15rem",
          }}
        >
          <p className="mb-1 font-medium text-popover-foreground">
            Coorte {formatMonthShort(hover.cohort.cohort_month)} · M
            {hover.point.months_since}
            {hover.partial && (
              <span className="ml-1.5 text-gold-600 dark:text-gold-400">
                · parcial
              </span>
            )}
          </p>
          <dl className="grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5 tabular-nums">
            <dt className="text-muted-foreground">Retenção</dt>
            <dd className="text-right font-medium text-popover-foreground">
              {formatPercent(hover.point.retention_rate)}
            </dd>
            <dt className="text-muted-foreground">Ativos</dt>
            <dd className="text-right text-popover-foreground">
              {formatNumber(hover.point.active_households)} de{" "}
              {formatNumber(hover.cohort.cohort_size)}
            </dd>
            <dt className="text-muted-foreground">Mês</dt>
            <dd className="text-right text-popover-foreground">
              {formatMonthShort(hover.point.activity_month)}
            </dd>
          </dl>
          {hover.partial && (
            <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">
              Mês-fronteira parcial — taxa subestimada, não é churn.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function CohortRow({
  cohort,
  columns,
  byMonth,
  partialMonth,
  theme,
  onHover,
}: {
  cohort: Cohort;
  columns: number[];
  byMonth: Map<number, CohortPoint>;
  partialMonth: string;
  theme: "light" | "dark";
  onHover: (h: HoverState | null) => void;
}) {
  return (
    <>
      <div className="sticky left-0 z-10 flex items-baseline gap-1.5 bg-card px-1 py-1">
        <span className="font-medium text-foreground">
          {formatMonthShort(cohort.cohort_month)}
        </span>
        <span className="text-[10px] tabular-nums text-muted-foreground">
          {formatNumber(cohort.cohort_size)}
        </span>
      </div>
      {columns.map((m) => {
        const point = byMonth.get(m);
        if (!point) {
          return <div key={`${cohort.cohort_month}-${m}`} aria-hidden />;
        }
        const partial = point.activity_month.slice(0, 7) === partialMonth;
        const { bg, fg } = retentionColor(point.retention_rate, theme);
        return (
          <button
            key={`${cohort.cohort_month}-${m}`}
            type="button"
            aria-label={`Coorte ${formatMonthShort(cohort.cohort_month)}, M${m}: ${formatPercent(
              point.retention_rate,
            )}${partial ? " (mês parcial)" : ""}`}
            className={cn(
              "flex h-9 items-center justify-center rounded-[5px] tabular-nums transition-[outline] outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
              partial && "border border-dashed border-gold-500/70",
            )}
            style={{ backgroundColor: bg, color: fg }}
            onMouseMove={(e) =>
              onHover({
                cohort,
                point,
                partial,
                x: e.clientX,
                y: e.clientY,
              })
            }
            onMouseEnter={(e) =>
              onHover({
                cohort,
                point,
                partial,
                x: e.clientX,
                y: e.clientY,
              })
            }
            onFocus={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              onHover({
                cohort,
                point,
                partial,
                x: r.left + r.width / 2,
                y: r.top,
              });
            }}
            onBlur={() => onHover(null)}
          >
            <span className="text-[10px] font-medium">
              {Math.round(point.retention_rate * 100)}
            </span>
          </button>
        );
      })}
    </>
  );
}

function HeatmapLegend({ theme }: { theme: "light" | "dark" }) {
  const from = retentionColor(0, theme).bg;
  const mid = retentionColor(0.5, theme).bg;
  const to = retentionColor(1, theme).bg;
  return (
    <div className="mt-4 flex items-center gap-3 text-[11px] text-muted-foreground">
      <span>Retenção</span>
      <span>0%</span>
      <span
        className="h-2.5 w-40 rounded-full"
        style={{
          background: `linear-gradient(to right, ${from}, ${mid}, ${to})`,
        }}
        aria-hidden
      />
      <span>100%</span>
      <span className="ml-2 inline-flex items-center gap-1.5">
        <span
          className="h-3 w-3 rounded-[4px] border border-dashed border-gold-500/70"
          aria-hidden
        />
        mês parcial
      </span>
    </div>
  );
}
