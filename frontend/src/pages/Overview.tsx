import { TrendingUp } from "lucide-react";

import { BentoCard } from "@/components/BentoCard";
import { RevenueWeeklyChart } from "@/components/RevenueWeeklyChart";
import { RfmSegmentsChart } from "@/components/RfmSegmentsChart";
import { StatTile } from "@/components/StatTile";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import {
  useMeta,
  useOverview,
  useRevenueWeekly,
  useRfmSegments,
} from "@/hooks/queries";
import {
  formatAsOfDate,
  formatCurrency,
  formatNumber,
  formatPercent,
} from "@/lib/format";

export function Overview() {
  const overview = useOverview();
  const weekly = useRevenueWeekly();
  const rfm = useRfmSegments();
  const meta = useMeta();

  const champions = rfm.data?.segments.find((s) => s.segment === "Campeões");
  const asOf = overview.data?.as_of_date;

  return (
    <div className="mx-auto max-w-[1400px]">
      {/* Cabeçalho da história analítica: contexto */}
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Visão geral do painel
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Leitura da receita observada, do ritmo semanal de compra e da
          concentração de valor por segmento RFM — sobre a amostra de domicílios
          de fidelidade do painel 84.51°/dunnhumby.
          {asOf && (
            <>
              {" "}
              Dados posicionados em{" "}
              <span className="font-medium text-foreground">
                {formatAsOfDate(asOf)}
              </span>
              .
            </>
          )}
        </p>
      </header>

      {/* Bento grid: tiles de tamanhos variados */}
      <div className="grid auto-rows-min grid-cols-1 gap-4 md:grid-cols-4">
        {/* HERO — receita observada total */}
        <BentoCard
          emphasis="hero"
          span={2}
          label="Receita observada total"
          className="min-h-[20rem] justify-between"
        >
          {overview.isPending ? (
            <LoadingState />
          ) : overview.isError ? (
            <ErrorState error={overview.error} />
          ) : (
            <>
              <StatTile
                size="hero"
                tone="accent"
                value={formatCurrency(overview.data.total_revenue)}
                sublabel={
                  <>Receita acumulada no período do dataset (USD)</>
                }
              />
              <p className="mt-6 text-xs leading-relaxed text-teal-100/70">
                Posição em {formatAsOfDate(overview.data.as_of_date)}. Amostra de{" "}
                {formatNumber(overview.data.household_universe)} domicílios do
                painel 84.51° — não representa o faturamento total da rede.
              </p>
            </>
          )}
        </BentoCard>

        {/* Série semanal de receita */}
        <BentoCard
          span={2}
          label="Receita semanal observada"
          headerRight={
            weekly.data ? `${formatNumber(weekly.data.n_weeks)} semanas` : null
          }
          className="min-h-[20rem]"
        >
          <div className="h-full min-h-[15rem] flex-1">
            {weekly.isPending ? (
              <LoadingState />
            ) : weekly.isError ? (
              <ErrorState error={weekly.error} />
            ) : weekly.data.series.length === 0 ? (
              <EmptyState>Sem série semanal publicada.</EmptyState>
            ) : (
              <RevenueWeeklyChart series={weekly.data.series} />
            )}
          </div>
        </BentoCard>

        {/* Ticket médio por cesta */}
        <BentoCard label="Ticket médio por cesta" className="min-h-[9rem]">
          {overview.isPending ? (
            <LoadingState />
          ) : overview.isError ? (
            <ErrorState error={overview.error} />
          ) : (
            <StatTile
              size="lg"
              value={formatCurrency(overview.data.avg_basket_value)}
              sublabel="Receita ÷ nº de cestas"
            />
          )}
        </BentoCard>

        {/* Domicílios ativos */}
        <BentoCard label="Domicílios ativos" className="min-h-[9rem]">
          {overview.isPending ? (
            <LoadingState />
          ) : overview.isError ? (
            <ErrorState error={overview.error} />
          ) : (
            <StatTile
              size="lg"
              value={formatNumber(overview.data.n_active_households)}
              sublabel={`de ${formatNumber(
                overview.data.household_universe,
              )} no painel`}
            />
          )}
        </BentoCard>

        {/* Nº de cestas */}
        <BentoCard label="Nº de cestas" className="min-h-[9rem]">
          {overview.isPending ? (
            <LoadingState />
          ) : overview.isError ? (
            <ErrorState error={overview.error} />
          ) : (
            <StatTile
              size="lg"
              value={formatNumber(overview.data.n_baskets)}
              sublabel="Tickets no período"
            />
          )}
        </BentoCard>

        {/* Insight âmbar — concentração de receita (Pareto RFM) */}
        <BentoCard
          emphasis="accent"
          label="Concentração de receita"
          className="min-h-[9rem]"
        >
          {rfm.isPending ? (
            <LoadingState />
          ) : rfm.isError ? (
            <ErrorState error={rfm.error} />
          ) : champions ? (
            <StatTile
              size="lg"
              tone="accent"
              value={formatPercent(champions.monetary_share)}
              sublabel={
                <>
                  da receita vem dos{" "}
                  <span className="font-medium text-foreground">Campeões</span> —{" "}
                  {formatPercent(champions.household_share)} dos domicílios
                </>
              }
            />
          ) : (
            <EmptyState>Segmento Campeões não encontrado.</EmptyState>
          )}
        </BentoCard>

        {/* Distribuição RFM */}
        <BentoCard
          span={3}
          label="Distribuição por segmento RFM"
          headerRight={
            rfm.data
              ? `${formatNumber(rfm.data.n_households_total)} domicílios`
              : null
          }
          className="min-h-[20rem]"
        >
          <div className="h-full min-h-[16rem] flex-1">
            {rfm.isPending ? (
              <LoadingState />
            ) : rfm.isError ? (
              <ErrorState error={rfm.error} />
            ) : rfm.data.segments.length === 0 ? (
              <EmptyState>Nenhum segmento publicado.</EmptyState>
            ) : (
              <RfmSegmentsChart segments={rfm.data.segments} />
            )}
          </div>
        </BentoCard>

        {/* Interpretação / oportunidade */}
        <BentoCard span={1} label="Leitura" className="min-h-[20rem]">
          <div className="flex h-full flex-col gap-3 text-sm leading-relaxed text-muted-foreground">
            <TrendingUp className="h-5 w-5 text-primary" aria-hidden />
            <p>
              O valor é fortemente concentrado: poucos{" "}
              <span className="font-medium text-foreground">Campeões</span>{" "}
              respondem por quase metade da receita, enquanto a cauda{" "}
              <span className="font-medium text-foreground">
                Hibernando / Perdidos
              </span>{" "}
              é numerosa, mas pouco contribui.
            </p>
            <p>
              Oportunidade: proteger os Campeões (retenção/benefícios) e desenhar
              reativação para quem está{" "}
              <span className="font-medium text-foreground">Em risco</span> antes
              que migre para a cauda.
            </p>
            <p className="mt-auto text-xs">
              Correlação não é causalidade: segmentos descrevem o passado
              observado, não o efeito de uma ação.
            </p>
          </div>
        </BentoCard>
      </div>

      {/* Rodapé discreto — proveniência do snapshot + escopo */}
      <footer className="mt-6 flex flex-col gap-1 border-t border-border pt-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <span>
          {meta.data ? (
            <>
              Snapshot{" "}
              <span className="font-medium text-foreground">
                {meta.data.snapshot_version}
              </span>{" "}
              · schema v{meta.data.schema_version} · commit {meta.data.git_commit}
            </>
          ) : (
            "Carregando metadados do snapshot…"
          )}
        </span>
        <span>
          Amostra do painel 84.51°/dunnhumby — não é o faturamento da rede.
        </span>
      </footer>
    </div>
  );
}
