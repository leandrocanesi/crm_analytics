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
import type { CampaignTypeRow } from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/format";

/**
 * Taxa de resgate por tipo de campanha (A/B/C). Barras horizontais, ordenadas
 * pela própria resposta. Comparar tipos exige a TAXA, não o volume bruto (um
 * tipo pode ter mais resgates só por ter sido enviado a mais gente). Type A
 * recebe o acento âmbar por ter a maior taxa — a cor segue ESSA entidade.
 *
 * ATENÇÃO (não-aditividade): expostos/resgatadores NÃO somam entre tipos (um
 * mesmo lar pode estar em campanhas de >1 tipo). Por isso este gráfico mostra a
 * TAXA (não empilha volumes) e o aviso vive ao lado dele na página.
 */
const TYPE_LABELS: Record<string, string> = {
  "Type A": "Tipo A",
  "Type B": "Tipo B",
  "Type C": "Tipo C",
};

function shortLabel(campaignType: string): string {
  return TYPE_LABELS[campaignType] ?? campaignType;
}

export function CampaignTypeChart({ types }: { types: CampaignTypeRow[] }) {
  const colors = useChartColors();
  const topRate = types.reduce(
    (max, t) => Math.max(max, t.redemption_rate),
    0,
  );

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={types}
        layout="vertical"
        margin={{ top: 4, right: 56, bottom: 4, left: 4 }}
        barCategoryGap={12}
      >
        <XAxis type="number" domain={[0, topRate * 1.15]} hide />
        <YAxis
          type="category"
          dataKey="campaign_type"
          tickLine={false}
          axisLine={false}
          width={64}
          tick={{ fill: colors.axis, fontSize: 12 }}
          tickFormatter={shortLabel}
        />
        <Tooltip
          cursor={{ fill: colors.grid, fillOpacity: 0.3 }}
          content={<TypeTooltip />}
        />
        <Bar
          dataKey="redemption_rate"
          radius={[0, 4, 4, 0]}
          barSize={28}
          isAnimationActive={false}
        >
          {types.map((t) => (
            <Cell
              key={t.campaign_type}
              fill={
                t.redemption_rate === topRate ? colors.accent : colors.revenue
              }
            />
          ))}
          <LabelList
            dataKey="redemption_rate"
            position="right"
            className="fill-muted-foreground"
            style={{ fontSize: 12, fontVariantNumeric: "tabular-nums" }}
            formatter={(v: number) => formatPercent(v)}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: CampaignTypeRow }[];
}

function TypeTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const t = payload[0]?.payload;
  if (!t) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-popover-foreground">
        {t.campaign_type}{" "}
        <span className="font-normal text-muted-foreground">
          · {formatNumber(t.n_campaigns)}{" "}
          {t.n_campaigns === 1 ? "campanha" : "campanhas"}
        </span>
      </p>
      <dl className="grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5 tabular-nums">
        <dt className="text-muted-foreground">Taxa de resgate</dt>
        <dd className="text-right font-medium text-popover-foreground">
          {formatPercent(t.redemption_rate)}
        </dd>
        <dt className="text-muted-foreground">Expostos</dt>
        <dd className="text-right text-popover-foreground">
          {formatNumber(t.households_exposed)}
        </dd>
        <dt className="text-muted-foreground">Resgataram</dt>
        <dd className="text-right text-popover-foreground">
          {formatNumber(t.households_redeemed)}
        </dd>
        <dt className="text-muted-foreground">Eventos de resgate</dt>
        <dd className="text-right text-popover-foreground">
          {formatNumber(t.n_redemption_events)}
        </dd>
      </dl>
    </div>
  );
}
