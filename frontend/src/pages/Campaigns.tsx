import { ArrowDown, ArrowUp, ArrowUpDown, Megaphone } from "lucide-react";
import { useMemo, useState } from "react";

import { BentoCard } from "@/components/BentoCard";
import { CampaignOverlapChart } from "@/components/CampaignOverlapChart";
import { CampaignTypeChart } from "@/components/CampaignTypeChart";
import { StatTile } from "@/components/StatTile";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCampaignOverlap,
  useCampaignPerformance,
  useCampaignsByType,
  useMeta,
} from "@/hooks/queries";
import type {
  CampaignPerformanceRow,
  CampaignSortField,
  SortOrder,
} from "@/lib/api";
import {
  formatAsOfDate,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import { cn } from "@/lib/utils";

/** Rótulo curto (A/B/C) para a UI; o dado real continua "Type A" etc. */
function shortType(campaignType: string): string {
  return campaignType.replace(/^Type\s+/, "");
}

/** Type A recebe o acento âmbar (maior taxa de resgate); B/C ficam teal. */
function isAccentType(campaignType: string): boolean {
  return campaignType === "Type A";
}

export function Campaigns() {
  const performance = useCampaignPerformance();
  const byType = useCampaignsByType();
  const overlap = useCampaignOverlap();
  const meta = useMeta();

  const [sortBy, setSortBy] = useState<CampaignSortField>("households_exposed");
  const [order, setOrder] = useState<SortOrder>("desc");

  const asOf =
    performance.data?.as_of_date ??
    overlap.data?.as_of_date ??
    byType.data?.as_of_date;

  /** Clique num cabeçalho ordenável: alterna asc/desc ou troca de coluna (desc). */
  function toggleSort(field: CampaignSortField) {
    if (field === sortBy) {
      setOrder((prev) => (prev === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(field);
      setOrder("desc");
    }
  }

  const rows = useMemo(() => {
    const data = performance.data?.campaigns ?? [];
    const sorted = [...data].sort((a, b) => {
      const diff = a[sortBy] - b[sortBy];
      return order === "desc" ? -diff : diff;
    });
    return sorted;
  }, [performance.data, sortBy, order]);

  const maxRate = useMemo(
    () => rows.reduce((max, r) => Math.max(max, r.redemption_rate), 0),
    [rows],
  );

  return (
    <div className="mx-auto max-w-[1400px]">
      {/* Contexto */}
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Inteligência de campanhas
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Quem foi alvo das campanhas de cupom, quanta sobreposição houve entre
          elas e com que frequência os domicílios resgataram — uma leitura
          puramente factual e observacional do painel 84.51°/dunnhumby.{" "}
          <span className="font-medium text-foreground">
            Sem valores monetários
          </span>
          : os dados não permitem atribuir receita a campanha, então nenhum R$
          aparece aqui.
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

      {/* Topo: alcance e sobreposição */}
      <div className="mb-6 grid auto-rows-min grid-cols-1 gap-4 md:grid-cols-4">
        <BentoCard
          emphasis="hero"
          label="Domicílios alcançados"
          className="min-h-[11rem] justify-center"
        >
          {overlap.isPending ? (
            <LoadingState />
          ) : overlap.isError ? (
            <ErrorState error={overlap.error} />
          ) : (
            <StatTile
              size="hero"
              tone="onHero"
              value={formatPercent(overlap.data.exposure_rate)}
              sublabel={
                <>
                  {formatNumber(overlap.data.total_exposed)} de{" "}
                  {formatNumber(overlap.data.universe)} domicílios foram alvo de
                  ≥1 campanha
                </>
              }
            />
          )}
        </BentoCard>

        <div className="flex flex-col gap-4">
          <BentoCard label="Campanhas" className="min-h-[5.25rem] justify-center">
            {performance.isPending ? (
              <LoadingState />
            ) : performance.isError ? (
              <ErrorState error={performance.error} />
            ) : (
              <StatTile
                size="lg"
                value={formatNumber(performance.data.n_campaigns)}
                sublabel="no período do painel"
              />
            )}
          </BentoCard>
          <BentoCard
            emphasis="accent"
            label="Média por lar"
            className="min-h-[5.25rem] justify-center"
          >
            {overlap.isPending ? (
              <LoadingState />
            ) : overlap.isError ? (
              <ErrorState error={overlap.error} />
            ) : (
              <StatTile
                size="lg"
                tone="accent"
                value={formatNumber(overlap.data.avg_campaigns_per_household, 2)}
                sublabel={`até ${formatNumber(
                  overlap.data.max_campaigns_per_household,
                )} campanhas no mesmo lar`}
              />
            )}
          </BentoCard>
        </div>

        <BentoCard
          span={2}
          label="Sobreposição: campanhas por domicílio"
          headerRight={
            overlap.data
              ? `${formatNumber(overlap.data.total_exposed)} alvejados`
              : null
          }
          className="min-h-[15rem]"
        >
          <div className="h-full min-h-[11rem] flex-1">
            {overlap.isPending ? (
              <LoadingState />
            ) : overlap.isError ? (
              <ErrorState error={overlap.error} />
            ) : overlap.data.distribution.length === 0 ? (
              <EmptyState>Sem distribuição publicada.</EmptyState>
            ) : (
              <CampaignOverlapChart
                distribution={overlap.data.distribution}
                avg={overlap.data.avg_campaigns_per_household}
              />
            )}
          </div>
        </BentoCard>
      </div>

      {/* Meio: resgate por tipo */}
      <div className="mb-6 grid auto-rows-min grid-cols-1 gap-4 md:grid-cols-3">
        <BentoCard
          span={2}
          label="Taxa de resgate por tipo de campanha"
          headerRight={byType.data ? `${byType.data.types.length} tipos` : null}
          className="min-h-[16rem]"
        >
          <div className="h-full min-h-[11rem] flex-1">
            {byType.isPending ? (
              <LoadingState />
            ) : byType.isError ? (
              <ErrorState error={byType.error} />
            ) : byType.data.types.length === 0 ? (
              <EmptyState>Sem dados por tipo.</EmptyState>
            ) : (
              <CampaignTypeChart types={byType.data.types} />
            )}
          </div>
        </BentoCard>

        {/* Aviso de não-aditividade, colado ao gráfico que parece somável */}
        <BentoCard
          label="Por que não somar os tipos"
          className="min-h-[16rem]"
        >
          <div className="flex h-full flex-col gap-3 text-xs leading-relaxed text-muted-foreground">
            <Megaphone className="h-5 w-5 text-primary" aria-hidden />
            <p>
              Expostos e resgatadores{" "}
              <span className="font-medium text-foreground">
                não são aditivos
              </span>{" "}
              entre os tipos: um mesmo domicílio pode estar em campanhas de mais
              de um tipo, então somá-los conta o lar mais de uma vez.
            </p>
            <p>
              Só os{" "}
              <span className="font-medium text-foreground">
                eventos de resgate
              </span>{" "}
              somam entre tipos. Compare tipos pela{" "}
              <span className="font-medium text-foreground">taxa</span>, nunca
              pelo volume bruto — um tipo pode ter mais resgates só por ter sido
              enviado a mais gente.
            </p>
            <p className="mt-auto">
              A/B/C são rótulos opacos de público diferente, sem aleatorização:
              não são comparáveis como “A converte mais”.
            </p>
          </div>
        </BentoCard>
      </div>

      {/* Base: desempenho por campanha */}
      <section className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-3">
          <h2 className="text-sm font-medium text-foreground">
            Desempenho por campanha
          </h2>
          <span className="text-xs tabular-nums text-muted-foreground">
            {performance.isPending
              ? "carregando…"
              : `${formatNumber(rows.length)} campanhas`}
          </span>
        </div>

        <div className="overflow-x-auto">
          {performance.isPending ? (
            <TableSkeleton />
          ) : performance.isError ? (
            <div className="p-6">
              <ErrorState error={performance.error} />
            </div>
          ) : rows.length === 0 ? (
            <div className="p-6">
              <EmptyState title="Nenhuma campanha">
                Nenhuma campanha publicada no snapshot.
              </EmptyState>
            </div>
          ) : (
            <table className="w-full min-w-[52rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-5 py-2.5 text-left font-medium">
                    Campanha
                  </th>
                  <th className="px-5 py-2.5 text-left font-medium">Tipo</th>
                  <th className="px-5 py-2.5 text-left font-medium">Período</th>
                  <SortHeader
                    label="Expostos"
                    field="households_exposed"
                    activeField={sortBy}
                    order={order}
                    onSort={toggleSort}
                  />
                  <SortHeader
                    label="Resgataram"
                    field="households_redeemed"
                    activeField={sortBy}
                    order={order}
                    onSort={toggleSort}
                  />
                  <SortHeader
                    label="Taxa de resgate"
                    field="redemption_rate"
                    activeField={sortBy}
                    order={order}
                    onSort={toggleSort}
                  />
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <CampaignRow
                    key={c.campaign_id}
                    campaign={c}
                    maxRate={maxRate}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Disclaimers (notes da API) */}
      <section className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-5 text-sm leading-relaxed text-muted-foreground shadow-sm">
          <Megaphone className="h-5 w-5 text-primary" aria-hidden />
          <p>
            Cerca de dois terços do painel foram alvo de ao menos uma campanha,
            com forte sobreposição: o lar típico recebeu ~4 campanhas. Type A
            (poucas campanhas, público amplo) tem a maior taxa de resgate.
          </p>
          <p>
            Oportunidade: investigar fadiga de contato nos lares muito
            alvejados e desenhar testes com grupo de controle — hoje não há
            como separar efeito de qualidade prévia do cliente.
          </p>
        </div>

        <div className="rounded-lg border border-border bg-card p-5 text-xs leading-relaxed text-muted-foreground shadow-sm">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-foreground">
            Exposição ≠ efeito · resgate ≠ conversão
          </h3>
          <p>
            {overlap.data?.note ??
              "Ser alvo não é ter visto/engajado. Quem resgata provavelmente já compraria (autosseleção) e não há grupo de controle aleatorizado. Os 36,9% nunca alvejados não são um controle válido."}
          </p>
        </div>

        <div className="rounded-lg border border-border bg-card p-5 text-xs leading-relaxed text-muted-foreground shadow-sm">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-foreground">
            Sem receita · correlação ≠ causalidade
          </h3>
          <p>
            {byType.data?.note ??
              "Não há atribuição de receita a campanha nos dados (coupon_disc não traz coupon_upc), por isso nenhuma métrica monetária aqui. Expostos/resgatadores não somam entre tipos; só os eventos de resgate são aditivos."}
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
          Amostra do painel 84.51°/dunnhumby — leitura observacional, sem receita
          atribuída.
        </span>
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subcomponentes
// ---------------------------------------------------------------------------

function SortHeader({
  label,
  field,
  activeField,
  order,
  onSort,
}: {
  label: string;
  field: CampaignSortField;
  activeField: CampaignSortField;
  order: SortOrder;
  onSort: (field: CampaignSortField) => void;
}) {
  const isActive = field === activeField;
  const Icon = !isActive ? ArrowUpDown : order === "desc" ? ArrowDown : ArrowUp;
  return (
    <th className="px-5 py-2.5 text-right font-medium">
      <button
        type="button"
        onClick={() => onSort(field)}
        aria-label={`Ordenar por ${label}`}
        className={cn(
          "ml-auto inline-flex items-center gap-1 transition-colors hover:text-foreground",
          isActive ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {label}
        <Icon
          className={cn("h-3 w-3", isActive ? "opacity-100" : "opacity-40")}
          aria-hidden
        />
      </button>
    </th>
  );
}

function CampaignRow({
  campaign: c,
  maxRate,
}: {
  campaign: CampaignPerformanceRow;
  maxRate: number;
}) {
  const accent = isAccentType(c.campaign_type);
  const barWidth = maxRate > 0 ? (c.redemption_rate / maxRate) * 100 : 0;
  return (
    <tr className="border-b border-border/60 last:border-0 transition-colors hover:bg-muted/40">
      <td className="px-5 py-2.5 font-medium tabular-nums text-foreground">
        #{c.campaign_id}
      </td>
      <td className="px-5 py-2.5">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 whitespace-nowrap text-xs",
            accent
              ? "font-medium text-gold-600 dark:text-gold-400"
              : "text-muted-foreground",
          )}
          title={c.campaign_type}
        >
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              accent ? "bg-gold-500" : "bg-teal-500",
            )}
            aria-hidden
          />
          {shortType(c.campaign_type)}
        </span>
      </td>
      <td className="px-5 py-2.5 whitespace-nowrap tabular-nums text-muted-foreground">
        {formatAsOfDate(c.start_date)}
        <span className="mx-1 opacity-50">→</span>
        {formatAsOfDate(c.end_date)}
      </td>
      <td className="px-5 py-2.5 text-right tabular-nums text-foreground">
        {formatNumber(c.households_exposed)}
      </td>
      <td className="px-5 py-2.5 text-right tabular-nums text-foreground">
        {formatNumber(c.households_redeemed)}
      </td>
      <td className="px-5 py-2.5">
        <div className="flex items-center justify-end gap-2">
          <div
            className="h-1.5 w-20 overflow-hidden rounded-full bg-muted"
            aria-hidden
          >
            <div
              className={cn(
                "h-full rounded-full",
                accent ? "bg-gold-500" : "bg-teal-500",
              )}
              style={{ width: `${barWidth}%` }}
            />
          </div>
          <span className="w-14 text-right tabular-nums text-foreground">
            {formatPercent(c.redemption_rate)}
          </span>
        </div>
      </td>
    </tr>
  );
}

function TableSkeleton() {
  return (
    <div
      className="divide-y divide-border/60"
      role="status"
      aria-label="Carregando campanhas"
    >
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-3">
          <Skeleton className="h-4 w-12" />
          <Skeleton className="h-4 w-14" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="ml-auto h-4 w-16" />
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-28" />
        </div>
      ))}
    </div>
  );
}
