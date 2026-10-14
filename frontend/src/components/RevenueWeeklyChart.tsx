import { useId } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useChartColors } from "@/hooks/useChartColors";
import type { WeeklyRevenuePoint } from "@/lib/api";
import {
  formatCurrency,
  formatCurrencyCompact,
  formatNumber,
} from "@/lib/format";

/**
 * Série semanal de receita observada (53 semanas do dataset).
 * Forma: área de uma única série (magnitude ao longo do tempo) — sem legenda
 * (um único tom teal; o título do tile já nomeia o que está plotado).
 * Marca: linha 2px teal + wash de gradiente ~10% (decisões da skill dataviz).
 */
export function RevenueWeeklyChart({
  series,
}: {
  series: WeeklyRevenuePoint[];
}) {
  const colors = useChartColors();
  const gradientId = useId();

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart
        data={series}
        margin={{ top: 8, right: 12, bottom: 4, left: 4 }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colors.washFrom} />
            <stop offset="100%" stopColor={colors.washTo} />
          </linearGradient>
        </defs>
        <CartesianGrid
          stroke={colors.grid}
          strokeWidth={1}
          vertical={false}
        />
        <XAxis
          dataKey="week"
          tickLine={false}
          axisLine={{ stroke: colors.grid }}
          tick={{ fill: colors.axis, fontSize: 11 }}
          interval={6}
          tickFormatter={(week: number) => `S${week}`}
          minTickGap={8}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={56}
          tick={{ fill: colors.axis, fontSize: 11 }}
          tickFormatter={(v: number) => formatCurrencyCompact(v)}
        />
        <Tooltip
          cursor={{ stroke: colors.axis, strokeWidth: 1 }}
          content={<RevenueTooltip />}
        />
        <Area
          type="monotone"
          dataKey="revenue"
          stroke={colors.revenue}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          activeDot={{
            r: 4,
            fill: colors.revenue,
            stroke: colors.washTo,
            strokeWidth: 2,
          }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: WeeklyRevenuePoint }[];
}

function RevenueTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0]?.payload;
  if (!point) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-popover-foreground">
        Semana {point.week}
      </p>
      <dl className="grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5 tabular-nums">
        <dt className="text-muted-foreground">Receita</dt>
        <dd className="text-right font-medium text-popover-foreground">
          {formatCurrency(point.revenue)}
        </dd>
        <dt className="text-muted-foreground">Cestas</dt>
        <dd className="text-right text-popover-foreground">
          {formatNumber(point.n_baskets)}
        </dd>
        <dt className="text-muted-foreground">Domicílios ativos</dt>
        <dd className="text-right text-popover-foreground">
          {formatNumber(point.n_active_households)}
        </dd>
        <dt className="text-muted-foreground">Ticket médio</dt>
        <dd className="text-right text-popover-foreground">
          {formatCurrency(point.avg_basket_value)}
        </dd>
      </dl>
    </div>
  );
}
