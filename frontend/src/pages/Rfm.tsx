import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useState } from "react";

import { BentoCard } from "@/components/BentoCard";
import { RfmSegmentsChart } from "@/components/RfmSegmentsChart";
import { StatTile } from "@/components/StatTile";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useMeta, useRfmHouseholds, useRfmSegments } from "@/hooks/queries";
import {
  RFM_SEGMENT_NAMES,
  type RfmHousehold,
  type RfmSegmentName,
  type RfmSortField,
  type SortOrder,
} from "@/lib/api";
import {
  formatAsOfDate,
  formatCurrency,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 25;
const CHAMPIONS: RfmSegmentName = "Campeões";

export function Rfm() {
  const [segment, setSegment] = useState<RfmSegmentName | undefined>(undefined);
  const [sortBy, setSortBy] = useState<RfmSortField>("monetary_value");
  const [order, setOrder] = useState<SortOrder>("desc");
  const [offset, setOffset] = useState(0);

  const segments = useRfmSegments();
  const households = useRfmHouseholds({
    segment,
    sortBy,
    order,
    limit: PAGE_SIZE,
    offset,
  });
  const meta = useMeta();

  const champions = segments.data?.segments.find(
    (s) => s.segment === CHAMPIONS,
  );
  const asOf = households.data?.as_of_date ?? segments.data?.as_of_date;

  /** Troca o filtro de segmento e volta para a primeira página. */
  function selectSegment(next: RfmSegmentName | undefined) {
    setSegment(next);
    setOffset(0);
  }

  /** Clique num cabeçalho ordenável: alterna asc/desc ou troca de coluna (desc). */
  function toggleSort(field: RfmSortField) {
    if (field === sortBy) {
      setOrder((prev) => (prev === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(field);
      setOrder("desc");
    }
    setOffset(0);
  }

  const total = households.data?.total ?? 0;
  const rows = households.data?.households ?? [];
  const rangeFrom = total === 0 ? 0 : offset + 1;
  const rangeTo = offset + rows.length;
  const canPrev = offset > 0;
  const canNext = offset + PAGE_SIZE < total;

  return (
    <div className="mx-auto max-w-[1400px]">
      {/* Contexto */}
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Segmentos RFM em detalhe
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Da distribuição dos 7 segmentos ao domicílio individual: recência,
          frequência e valor monetário de cada household do painel
          84.51°/dunnhumby. Filtre por segmento, ordene e navegue para investigar
          quem sustenta a receita.
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

      {/* Distribuição dos segmentos: contexto antes do detalhe */}
      <div className="mb-6 grid auto-rows-min grid-cols-1 gap-4 md:grid-cols-4">
        <BentoCard
          span={3}
          label="Distribuição por segmento RFM"
          headerRight={
            segments.data
              ? `${formatNumber(segments.data.n_households_total)} domicílios`
              : null
          }
          className="min-h-[19rem]"
        >
          <div className="h-full min-h-[15rem] flex-1">
            {segments.isPending ? (
              <LoadingState />
            ) : segments.isError ? (
              <ErrorState error={segments.error} />
            ) : segments.data.segments.length === 0 ? (
              <EmptyState>Nenhum segmento publicado.</EmptyState>
            ) : (
              <RfmSegmentsChart segments={segments.data.segments} />
            )}
          </div>
        </BentoCard>

        <BentoCard
          emphasis="accent"
          label="Concentração de receita"
          className="min-h-[19rem] justify-center"
        >
          {segments.isPending ? (
            <LoadingState />
          ) : segments.isError ? (
            <ErrorState error={segments.error} />
          ) : champions ? (
            <StatTile
              size="lg"
              tone="accent"
              value={formatPercent(champions.monetary_share)}
              sublabel={
                <>
                  da receita vem dos{" "}
                  <span className="font-medium text-foreground">Campeões</span> —{" "}
                  {formatNumber(champions.n_households)} domicílios (
                  {formatPercent(champions.household_share)})
                </>
              }
            />
          ) : (
            <EmptyState>Segmento Campeões não encontrado.</EmptyState>
          )}
        </BentoCard>
      </div>

      {/* Filtro por segmento */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <SegmentChip
          active={segment === undefined}
          onClick={() => selectSegment(undefined)}
        >
          Todos
          {segments.data && (
            <ChipCount>
              {formatNumber(segments.data.n_households_total)}
            </ChipCount>
          )}
        </SegmentChip>
        {RFM_SEGMENT_NAMES.map((name) => {
          const count = segments.data?.segments.find(
            (s) => s.segment === name,
          )?.n_households;
          return (
            <SegmentChip
              key={name}
              active={segment === name}
              accent={name === CHAMPIONS}
              onClick={() => selectSegment(name)}
            >
              {name}
              {count !== undefined && (
                <ChipCount>{formatNumber(count)}</ChipCount>
              )}
            </SegmentChip>
          );
        })}
      </div>

      {/* Tabela de domicílios */}
      <section className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-3">
          <h2 className="text-sm font-medium text-foreground">
            Domicílios
            <span className="ml-2 font-normal text-muted-foreground">
              {segment ?? "todos os segmentos"}
            </span>
          </h2>
          <span className="text-xs tabular-nums text-muted-foreground">
            {households.isPending
              ? "carregando…"
              : total === 0
                ? "0 domicílios"
                : `${formatNumber(rangeFrom)}–${formatNumber(
                    rangeTo,
                  )} de ${formatNumber(total)}`}
          </span>
        </div>

        <div className="overflow-x-auto">
          {households.isPending ? (
            <TableSkeleton />
          ) : households.isError ? (
            <div className="p-6">
              <ErrorState error={households.error} />
            </div>
          ) : rows.length === 0 ? (
            <div className="p-6">
              <EmptyState title="Nenhum domicílio">
                Nenhum domicílio bate o filtro selecionado.
              </EmptyState>
            </div>
          ) : (
            <table
              className={cn(
                "w-full min-w-[46rem] border-collapse text-sm",
                // durante refetch de página, esmaece levemente
                households.isFetching && "opacity-60 transition-opacity",
              )}
            >
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-5 py-2.5 text-left font-medium">
                    Household
                  </th>
                  <SortHeader
                    label="Recência (dias)"
                    field="recency_days"
                    activeField={sortBy}
                    order={order}
                    onSort={toggleSort}
                  />
                  <SortHeader
                    label="Frequência (cestas)"
                    field="frequency_baskets"
                    activeField={sortBy}
                    order={order}
                    onSort={toggleSort}
                  />
                  <SortHeader
                    label="Valor (USD)"
                    field="monetary_value"
                    activeField={sortBy}
                    order={order}
                    onSort={toggleSort}
                  />
                  <th className="px-5 py-2.5 text-center font-medium">R/F/M</th>
                  <th className="px-5 py-2.5 text-left font-medium">Segmento</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((h) => (
                  <HouseholdRow key={h.household_id} household={h} />
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Paginação (usa total do servidor, não rows.length) */}
        <div className="flex items-center justify-between gap-2 border-t border-border px-5 py-3">
          <span className="text-xs tabular-nums text-muted-foreground">
            {total > 0 &&
              `Página ${formatNumber(
                Math.floor(offset / PAGE_SIZE) + 1,
              )} de ${formatNumber(Math.max(1, Math.ceil(total / PAGE_SIZE)))}`}
          </span>
          <div className="flex gap-2">
            <PageButton
              disabled={!canPrev}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            >
              Anterior
            </PageButton>
            <PageButton
              disabled={!canNext}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
            >
              Próxima
            </PageButton>
          </div>
        </div>
      </section>

      {/* Disclaimer + proveniência */}
      <footer className="mt-6 flex flex-col gap-2 border-t border-border pt-4 text-xs text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">Como ler:</span> a
          recência é medida em dias até a data as-of (
          {asOf ? formatAsOfDate(asOf) : "2018-01-01"}), não até hoje — valores
          altos não comprovam churn (há left-censoring: o painel tem início e
          fim definidos).{" "}
          {households.data?.note ?? segments.data?.note}
        </p>
        {meta.data && (
          <p>
            Snapshot{" "}
            <span className="font-medium text-foreground">
              {meta.data.snapshot_version}
            </span>{" "}
            · schema v{meta.data.schema_version} · commit {meta.data.git_commit}
          </p>
        )}
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subcomponentes
// ---------------------------------------------------------------------------

function SegmentChip({
  active,
  accent,
  onClick,
  children,
}: {
  active: boolean;
  accent?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
        active
          ? accent
            ? "border-gold-500 bg-gold-500/15 text-gold-600 dark:text-gold-400"
            : "border-primary bg-primary text-primary-foreground"
          : "border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function ChipCount({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-background/40 px-1.5 text-[10px] tabular-nums opacity-80">
      {children}
    </span>
  );
}

function SortHeader({
  label,
  field,
  activeField,
  order,
  onSort,
}: {
  label: string;
  field: RfmSortField;
  activeField: RfmSortField;
  order: SortOrder;
  onSort: (field: RfmSortField) => void;
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

function HouseholdRow({ household: h }: { household: RfmHousehold }) {
  const isChampion = h.rfm_segment === CHAMPIONS;
  return (
    <tr
      className={cn(
        "border-b border-border/60 last:border-0 transition-colors hover:bg-muted/40",
        isChampion && "bg-gold-500/[0.06]",
      )}
    >
      <td className="px-5 py-2.5 font-medium tabular-nums text-foreground">
        {formatNumber(h.household_id)}
      </td>
      <td className="px-5 py-2.5 text-right tabular-nums text-foreground">
        {formatNumber(h.recency_days)}
      </td>
      <td className="px-5 py-2.5 text-right tabular-nums text-foreground">
        {formatNumber(h.frequency_baskets)}
      </td>
      <td className="px-5 py-2.5 text-right tabular-nums text-foreground">
        {formatCurrency(h.monetary_value)}
      </td>
      <td className="px-5 py-2.5">
        <div className="flex items-center justify-center gap-1">
          <ScoreBadge letter="R" value={h.r_score} />
          <ScoreBadge letter="F" value={h.f_score} />
          <ScoreBadge letter="M" value={h.m_score} />
        </div>
      </td>
      <td className="px-5 py-2.5">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 whitespace-nowrap text-xs",
            isChampion
              ? "font-medium text-gold-600 dark:text-gold-400"
              : "text-muted-foreground",
          )}
        >
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              isChampion ? "bg-gold-500" : "bg-teal-500",
            )}
            aria-hidden
          />
          {h.rfm_segment}
        </span>
      </td>
    </tr>
  );
}

/** Mini-badge do score (1..5). Mais escuro = score mais alto (teal). */
function ScoreBadge({ letter, value }: { letter: string; value: number }) {
  return (
    <span
      title={`${letter} = ${value}`}
      className="inline-flex h-6 min-w-[2.1rem] items-center justify-center gap-0.5 rounded border border-border bg-secondary px-1 text-[11px] font-medium tabular-nums text-secondary-foreground"
    >
      <span className="opacity-50">{letter}</span>
      {value}
    </span>
  );
}

function PageButton({
  disabled,
  onClick,
  children,
}: {
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "rounded-md border border-border px-3 py-1.5 text-xs font-medium transition-colors",
        disabled
          ? "cursor-not-allowed text-muted-foreground/40"
          : "text-foreground hover:bg-muted",
      )}
    >
      {children}
    </button>
  );
}

function TableSkeleton() {
  return (
    <div className="divide-y divide-border/60" role="status" aria-label="Carregando domicílios">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-3">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="ml-auto h-4 w-12" />
          <Skeleton className="h-4 w-12" />
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-6 w-28" />
          <Skeleton className="h-4 w-24" />
        </div>
      ))}
    </div>
  );
}
