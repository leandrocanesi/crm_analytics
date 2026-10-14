import { useId } from "react";
import {
  Area,
  ComposedChart,
  CartesianGrid,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useChartColors } from "@/hooks/useChartColors";
import type { RetentionMonthlyPoint } from "@/lib/api";
import { formatMonthShort, formatMonthYear, formatNumber, formatPercent } from "@/lib/format";

/**
 * Retenção mês-a-mês (% de ativos no mês M que voltam em M+1).
 * Forma: área de série única (magnitude ao longo do tempo), tom teal — mesma
 * linguagem da série de receita. Eixo Y em 0–100% (NÃO truncado: a variação
 * real é pequena, mas truncar o eixo exageraria enganosamente as diferenças).
 *
 * O ÚLTIMO mês (2017-12) é mês-fronteira parcial: a "queda" é artefato, não
 * churn. Por isso o traço final vira tracejado esmaecido + ponto âmbar anotado
 * "parcial", em vez de continuar a área cheia (que daria falsa impressão de
 * colapso de retenção).
 */

interface Row {
  month: string;
  rateSolid: number | null;
  rateBridge: number | null;
  point: RetentionMonthlyPoint;
}

function buildRows(series: RetentionMonthlyPoint[]): Row[] {
  const lastSolidIdx = series.reduce(
    (acc, p, i) => (p.next_month_partial ? acc : i),
    -1,
  );
  return series.map((p, i) => {
    const bridge = p.next_month_partial || i === lastSolidIdx;
    return {
      month: p.activity_month,
      rateSolid: p.next_month_partial ? null : p.retention_rate,
      rateBridge: bridge ? p.retention_rate : null,
      point: p,
    };
  });
}

export function RetentionMonthlyChart({
  series,
}: {
  series: RetentionMonthlyPoint[];
}) {
  const colors = useChartColors();
  const gradientId = useId();
  const rows = buildRows(series);
  const partial = series.find((p) => p.next_month_partial);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 12, right: 16, bottom: 4, left: 4 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colors.washFrom} />
            <stop offset="100%" stopColor={colors.washTo} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={colors.grid} strokeWidth={1} vertical={false} />
        <XAxis
          dataKey="month"
          tickLine={false}
          axisLine={{ stroke: colors.grid }}
          tick={{ fill: colors.axis, fontSize: 11 }}
          tickFormatter={(m: string) => formatMonthShort(m)}
          minTickGap={12}
        />
        <YAxis
          domain={[0, 1]}
          ticks={[0, 0.25, 0.5, 0.75, 1]}
          tickLine={false}
          axisLine={false}
          width={44}
          tick={{ fill: colors.axis, fontSize: 11 }}
          tickFormatter={(v: number) => formatPercent(v, 0)}
        />
        <Tooltip
          cursor={{ stroke: colors.axis, strokeWidth: 1 }}
          content={<RetentionTooltip />}
        />
        {/* Área cheia só sobre os meses completos */}
        <Area
          type="monotone"
          dataKey="rateSolid"
          stroke={colors.revenue}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          connectNulls={false}
          isAnimationActive={false}
          activeDot={{
            r: 4,
            fill: colors.revenue,
            stroke: colors.washTo,
            strokeWidth: 2,
          }}
        />
        {/* Ponte tracejada esmaecida ligando o último mês completo ao parcial */}
        <Line
          type="monotone"
          dataKey="rateBridge"
          stroke={colors.axis}
          strokeWidth={1.5}
          strokeDasharray="4 3"
          dot={false}
          connectNulls
          isAnimationActive={false}
        />
        {partial && (
          <ReferenceDot
            x={partial.activity_month}
            y={partial.retention_rate}
            r={4}
            fill={colors.accent}
            stroke={colors.washTo}
            strokeWidth={2}
            label={{
              value: `${formatMonthShort(partial.activity_month)} · parcial`,
              position: "top",
              fill: colors.accent,
              fontSize: 11,
            }}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: Row }[];
}

function RetentionTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  const p = row.point;
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-popover-foreground">
        {formatMonthYear(p.activity_month)}
        {p.next_month_partial && (
          <span className="ml-1.5 text-gold-600 dark:text-gold-400">· parcial</span>
        )}
      </p>
      <dl className="grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5 tabular-nums">
        <dt className="text-muted-foreground">Retenção M+1</dt>
        <dd className="text-right font-medium text-popover-foreground">
          {formatPercent(p.retention_rate)}
        </dd>
        <dt className="text-muted-foreground">Ativos no mês</dt>
        <dd className="text-right text-popover-foreground">
          {formatNumber(p.active_households)}
        </dd>
        <dt className="text-muted-foreground">Voltaram em M+1</dt>
        <dd className="text-right text-popover-foreground">
          {formatNumber(p.retained_next_month)}
        </dd>
      </dl>
      {p.next_month_partial && (
        <p className="mt-1.5 max-w-[14rem] text-[11px] leading-snug text-muted-foreground">
          Mês-fronteira: o mês seguinte só tem os primeiros dias do dataset. A
          queda é artefato, não churn.
        </p>
      )}
    </div>
  );
}
