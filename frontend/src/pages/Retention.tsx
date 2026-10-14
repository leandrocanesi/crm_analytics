import { Repeat2 } from "lucide-react";

import { BentoCard } from "@/components/BentoCard";
import { CohortHeatmap } from "@/components/CohortHeatmap";
import { RetentionMonthlyChart } from "@/components/RetentionMonthlyChart";
import { StatTile } from "@/components/StatTile";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { useMeta, useRetentionCohorts, useRetentionMonthly } from "@/hooks/queries";
import type { RetentionMonthlyPoint } from "@/lib/api";
import {
  formatAsOfDate,
  formatMonthYear,
  formatPercent,
} from "@/lib/format";

/** Média da retenção mensal, excluindo o mês-fronteira parcial. */
function averageRetention(series: RetentionMonthlyPoint[]): number | null {
  const full = series.filter((p) => !p.next_month_partial);
  if (full.length === 0) return null;
  const sum = full.reduce((acc, p) => acc + p.retention_rate, 0);
  return sum / full.length;
}

/** Mês de pico de retenção, ignorando o mês parcial. */
function peakMonth(series: RetentionMonthlyPoint[]): RetentionMonthlyPoint | null {
  const full = series.filter((p) => !p.next_month_partial);
  if (full.length === 0) return null;
  return full.reduce((best, p) =>
    p.retention_rate > best.retention_rate ? p : best,
  );
}

export function Retention() {
  const monthly = useRetentionMonthly();
  const cohorts = useRetentionCohorts();
  const meta = useMeta();

  const asOf = monthly.data?.as_of_date ?? cohorts.data?.as_of_date;
  const avg = monthly.data ? averageRetention(monthly.data.series) : null;
  const peak = monthly.data ? peakMonth(monthly.data.series) : null;

  return (
    <div className="mx-auto max-w-[1400px]">
      {/* Contexto */}
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Retenção de domicílios
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Quantos domicílios voltam a comprar mês após mês — a leitura mensal
          dá o pulso; o triângulo de coortes diagnostica como cada safra
          envelhece. Amostra de fidelidade do painel 84.51°/dunnhumby.
          {asOf && (
            <>
              {" "}
              Posição em{" "}
              <span className="font-medium text-foreground">
                {formatAsOfDate(asOf)}
              </span>
              .
            </>
          )}
        </p>
      </header>

      {/* Leitura primária: retenção mensal */}
      <div className="mb-6 grid auto-rows-min grid-cols-1 gap-4 md:grid-cols-4">
        <BentoCard
          span={3}
          label="Retenção mês a mês (M → M+1)"
          headerRight={
            monthly.data ? `${monthly.data.series.length} meses` : null
          }
          className="min-h-[22rem]"
        >
          <div className="h-full min-h-[17rem] flex-1">
            {monthly.isPending ? (
              <LoadingState />
            ) : monthly.isError ? (
              <ErrorState error={monthly.error} />
            ) : monthly.data.series.length === 0 ? (
              <EmptyState>Sem série mensal publicada.</EmptyState>
            ) : (
              <RetentionMonthlyChart series={monthly.data.series} />
            )}
          </div>
        </BentoCard>

        {/* Coluna de indicadores */}
        <div className="flex flex-col gap-4">
          <BentoCard
            emphasis="hero"
            label="Retenção mensal média"
            className="min-h-[10.5rem] justify-center"
          >
            {monthly.isPending ? (
              <LoadingState />
            ) : monthly.isError ? (
              <ErrorState error={monthly.error} />
            ) : avg !== null ? (
              <StatTile
                size="hero"
                tone="onHero"
                value={formatPercent(avg)}
                sublabel="média dos meses completos (exclui o mês parcial)"
              />
            ) : (
              <EmptyState>Sem meses completos.</EmptyState>
            )}
          </BentoCard>

          <BentoCard
            emphasis="accent"
            label="Mês de pico"
            className="min-h-[10.5rem] justify-center"
          >
            {monthly.isPending ? (
              <LoadingState />
            ) : monthly.isError ? (
              <ErrorState error={monthly.error} />
            ) : peak ? (
              <StatTile
                size="lg"
                tone="accent"
                value={formatPercent(peak.retention_rate)}
                sublabel={
                  <>
                    maior retenção, em{" "}
                    <span className="font-medium text-foreground">
                      {formatMonthYear(peak.activity_month)}
                    </span>
                  </>
                }
              />
            ) : (
              <EmptyState>Sem dados.</EmptyState>
            )}
          </BentoCard>
        </div>
      </div>

      {/* Disclaimer da leitura mensal */}
      {monthly.data && (
        <p className="mb-8 max-w-3xl text-xs leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">Como ler:</span> o
          último ponto (dez/2017) cai para perto de zero porque o mês seguinte
          (jan/2018) tem apenas os primeiros dias do dataset — é artefato de
          mês-fronteira, não churn. Por isso ele aparece tracejado e anotado
          como parcial, e fica de fora da média e do pico.
        </p>
      )}

      {/* Diagnóstico: heatmap de coortes */}
      <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-medium text-foreground">
              Retenção por coorte
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Cada linha é uma safra; a cor mostra a % que seguia ativa a cada
              mês desde a primeira compra.
            </p>
          </div>
          {cohorts.data && (
            <span className="text-xs tabular-nums text-muted-foreground">
              {cohorts.data.cohorts.length} coortes
            </span>
          )}
        </div>

        {cohorts.isPending ? (
          <div className="min-h-[18rem]">
            <LoadingState />
          </div>
        ) : cohorts.isError ? (
          <div className="min-h-[18rem]">
            <ErrorState error={cohorts.error} />
          </div>
        ) : cohorts.data.cohorts.length === 0 ? (
          <div className="min-h-[18rem]">
            <EmptyState>Nenhuma coorte publicada.</EmptyState>
          </div>
        ) : (
          <CohortHeatmap
            cohorts={cohorts.data.cohorts}
            asOfDate={cohorts.data.as_of_date}
          />
        )}
      </section>

      {/* Interpretação + disclaimers (notes da API) */}
      <section className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-5 text-sm leading-relaxed text-muted-foreground shadow-sm">
          <Repeat2 className="h-5 w-5 text-primary" aria-hidden />
          <p>
            A retenção mês a mês é alta e estável (~90%): a base recompra com
            regularidade. Nas coortes, a queda forte acontece de M0 para M1 e
            depois estabiliza — o padrão clássico de varejo de fidelidade.
          </p>
          <p>
            Oportunidade: o esforço de reativação rende mais no primeiro mês
            após a entrada, antes do platô.
          </p>
        </div>

        <div className="rounded-lg border border-border bg-card p-5 text-xs leading-relaxed text-muted-foreground shadow-sm">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-foreground">
            Left-censoring
          </h3>
          <p>
            {cohorts.data?.note ??
              "cohort_month = primeira aparição na janela de dados, NÃO a aquisição real. O dataset começa em jan/2017, então a coorte de janeiro concentra os já-clientes visíveis no início — não são novos de janeiro. Coortes tardias têm menos meses para maturar: não compare M12 entre coortes."}
          </p>
        </div>

        <div className="rounded-lg border border-border bg-card p-5 text-xs leading-relaxed text-muted-foreground shadow-sm">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-foreground">
            Mês-fronteira & causalidade
          </h3>
          <p>
            {monthly.data?.note ??
              "A queda dez→jan é mês-fronteira parcial, não churn."}
          </p>
          <p className="mt-2">
            Métrica observacional: descreve o comportamento passado, não o
            efeito de nenhuma ação de CRM. Correlação não é causalidade.
          </p>
        </div>
      </section>

      {/* Proveniência */}
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
