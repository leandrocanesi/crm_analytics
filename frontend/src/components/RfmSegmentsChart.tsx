import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useChartColors } from "@/hooks/useChartColors";
import type { RfmSegment } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/format";

/**
 * Distribuição dos 7 segmentos RFM por nº de domicílios (barras horizontais,
 * ordenadas desc — ranking de magnitude, tom teal único). O segmento
 * "Campeões" recebe o acento âmbar: é a história do RFM (poucos domicílios,
 * muita receita), então a cor segue ESSA entidade, de forma estável.
 */
const CHAMPIONS = "Campeões";

export function RfmSegmentsChart({ segments }: { segments: RfmSegment[] }) {
  const colors = useChartColors();

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={segments}
        layout="vertical"
        margin={{ top: 4, right: 56, bottom: 4, left: 4 }}
        barCategoryGap={8}
      >
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="segment"
          tickLine={false}
          axisLine={false}
          width={140}
          tick={{ fill: colors.axis, fontSize: 12 }}
        />
        <Tooltip
          cursor={{ fill: colors.grid, fillOpacity: 0.3 }}
          content={<RfmTooltip />}
        />
        <Bar
          dataKey="n_households"
          radius={[0, 4, 4, 0]}
          barSize={20}
          isAnimationActive={false}
        >
          {segments.map((s) => (
            <Cell
              key={s.segment}
              fill={s.segment === CHAMPIONS ? colors.accent : colors.revenue}
            />
          ))}
          <LabelList
            dataKey="n_households"
            position="right"
            className="fill-muted-foreground"
            style={{ fontSize: 11, fontVariantNumeric: "tabular-nums" }}
            formatter={(v: number) => formatNumber(v)}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: RfmSegment }[];
}

function RfmTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const seg = payload[0]?.payload;
  if (!seg) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-popover-foreground">{seg.segment}</p>
      <dl className="grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5 tabular-nums">
        <dt className="text-muted-foreground">Domicílios</dt>
        <dd className="text-right font-medium text-popover-foreground">
          {formatNumber(seg.n_households)} ({formatPercent(seg.household_share)})
        </dd>
        <dt className="text-muted-foreground">Receita (M)</dt>
        <dd className="text-right text-popover-foreground">
          {formatCurrency(seg.monetary_value)}
        </dd>
        <dt className="text-muted-foreground">Participação na receita</dt>
        <dd className="text-right text-popover-foreground">
          {formatPercent(seg.monetary_share)}
        </dd>
      </dl>
    </div>
  );
}
