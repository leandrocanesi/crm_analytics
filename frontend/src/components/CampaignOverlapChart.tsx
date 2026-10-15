import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useChartColors } from "@/hooks/useChartColors";
import type { CampaignOverlapPoint } from "@/lib/api";
import { formatNumber } from "@/lib/format";

/**
 * Sobreposição de campanhas: quantos domicílios foram alvo de N campanhas.
 * Forma: histograma de contagem (quantidade por faixa), tom teal ÚNICO — é
 * magnitude sequencial, não categorias que precisem de cores distintas. A
 * linha tracejada âmbar marca a média de campanhas por lar (acento escasso,
 * reservado ao destaque). Eixos não truncados.
 */
export function CampaignOverlapChart({
  distribution,
  avg,
}: {
  distribution: CampaignOverlapPoint[];
  avg: number;
}) {
  const colors = useChartColors();

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={distribution}
        margin={{ top: 16, right: 8, bottom: 4, left: 4 }}
        barCategoryGap={2}
      >
        <CartesianGrid stroke={colors.grid} strokeWidth={1} vertical={false} />
        <XAxis
          dataKey="n_campaigns_exposed"
          tickLine={false}
          axisLine={{ stroke: colors.grid }}
          tick={{ fill: colors.axis, fontSize: 11 }}
          interval={0}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={32}
          tick={{ fill: colors.axis, fontSize: 11 }}
          tickFormatter={(v: number) => formatNumber(v)}
        />
        <Tooltip
          cursor={{ fill: colors.grid, fillOpacity: 0.3 }}
          content={<OverlapTooltip />}
        />
        <ReferenceLine
          x={Math.round(avg)}
          stroke={colors.accent}
          strokeDasharray="4 3"
          strokeWidth={1.5}
          label={{
            value: `média ${formatNumber(avg, 2)}`,
            position: "top",
            fill: colors.accent,
            fontSize: 11,
          }}
        />
        <Bar
          dataKey="n_households"
          fill={colors.revenue}
          radius={[4, 4, 0, 0]}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: CampaignOverlapPoint }[];
}

function OverlapTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0]?.payload;
  if (!p) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-popover-foreground">
        {formatNumber(p.n_campaigns_exposed)}{" "}
        {p.n_campaigns_exposed === 1 ? "campanha" : "campanhas"}
      </p>
      <dl className="grid grid-cols-[auto_auto] gap-x-3 tabular-nums">
        <dt className="text-muted-foreground">Domicílios</dt>
        <dd className="text-right font-medium text-popover-foreground">
          {formatNumber(p.n_households)}
        </dd>
      </dl>
    </div>
  );
}
