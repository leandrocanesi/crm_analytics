/**
 * Cliente de API tipado do Customer Intelligence Lab.
 *
 * Regras do projeto:
 *  - O frontend NUNCA acessa o DuckDB direto; só consome esta API read-only.
 *  - Toda resposta é validada com zod (espelha os contratos Pydantic do backend).
 *  - O 503 (snapshot indisponível) é um estado de NEGÓCIO esperado, tratado como
 *    erro tipado (SnapshotUnavailableError) para a UI exibir a mensagem correta.
 */

import { z } from "zod";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Nota de escopo da amostra, reaproveitada nas respostas monetárias. */
export const SAMPLE_SCOPE_HINT =
  "amostra do painel 84.51°/dunnhumby — não é o faturamento da rede";

// ---------------------------------------------------------------------------
// Schemas (espelham backend/app/schemas.py)
// ---------------------------------------------------------------------------

export const healthSchema = z.object({
  status: z.string(),
  snapshot_available: z.boolean(),
  snapshot_version: z.string().nullable().optional(),
  schema_version: z.string().nullable().optional(),
});

export const metaSchema = z.object({
  schema_version: z.string(),
  snapshot_version: z.string(),
  built_at: z.string(),
  published_at: z.string().nullable().optional(),
  as_of_date: z.string(),
  revenue_total: z.number(),
  basket_count: z.number(),
  household_count: z.number(),
  currency: z.string(),
  git_commit: z.string(),
  content_hash: z.string(),
  tables: z.array(z.string()),
  note: z.string(),
});

export const overviewSchema = z.object({
  total_revenue: z.number(),
  n_active_households: z.number(),
  household_universe: z.number(),
  n_baskets: z.number(),
  avg_basket_value: z.number(),
  as_of_date: z.string(),
  currency: z.string(),
  note: z.string(),
});

export const weeklyRevenuePointSchema = z.object({
  week: z.number(),
  revenue: z.number(),
  n_baskets: z.number(),
  n_active_households: z.number(),
  avg_basket_value: z.number(),
});

export const weeklyRevenueSchema = z.object({
  as_of_date: z.string(),
  currency: z.string(),
  n_weeks: z.number(),
  total_revenue: z.number(),
  series: z.array(weeklyRevenuePointSchema),
  note: z.string(),
});

export const rfmSegmentSchema = z.object({
  segment: z.string(),
  n_households: z.number(),
  household_share: z.number(),
  monetary_value: z.number(),
  monetary_share: z.number(),
});

export const rfmSegmentsSchema = z.object({
  as_of_date: z.string(),
  currency: z.string(),
  n_segments: z.number(),
  n_households_total: z.number(),
  segments: z.array(rfmSegmentSchema),
  note: z.string(),
});

/** Nomes canônicos dos 7 segmentos RFM (eco do contrato do backend). */
export const RFM_SEGMENT_NAMES = [
  "Campeões",
  "Leais",
  "Potenciais",
  "Novos",
  "Em risco",
  "Hibernando / Perdidos",
  "Outros",
] as const;
export type RfmSegmentName = (typeof RFM_SEGMENT_NAMES)[number];

/** Colunas ordenáveis da tabela de domicílios. */
export const RFM_SORT_FIELDS = [
  "monetary_value",
  "recency_days",
  "frequency_baskets",
] as const;
export type RfmSortField = (typeof RFM_SORT_FIELDS)[number];
export type SortOrder = "asc" | "desc";

export const rfmHouseholdSchema = z.object({
  household_id: z.number(),
  recency_days: z.number(),
  frequency_baskets: z.number(),
  monetary_value: z.number(),
  r_score: z.number(),
  f_score: z.number(),
  m_score: z.number(),
  rfm_segment: z.string(),
});

export const rfmHouseholdsSchema = z.object({
  as_of_date: z.string(),
  currency: z.string(),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
  segment: z.string().nullable(),
  households: z.array(rfmHouseholdSchema),
  note: z.string(),
});

// ---------------------------------------------------------------------------
// Retenção (espelha GET /retention/monthly e /retention/cohorts)
// ---------------------------------------------------------------------------

export const retentionMonthlyPointSchema = z.object({
  /** Mês de atividade, ISO "YYYY-MM-01". */
  activity_month: z.string(),
  active_households: z.number(),
  retained_next_month: z.number(),
  /** Fração 0..1 (não %). */
  retention_rate: z.number(),
  /** true só no mês-fronteira (2017-12 → 2018-01 parcial): não é churn real. */
  next_month_partial: z.boolean(),
});

export const retentionMonthlySchema = z.object({
  as_of_date: z.string(),
  n_months: z.number(),
  series: z.array(retentionMonthlyPointSchema),
  note: z.string(),
});

export const cohortPointSchema = z.object({
  /** Meses desde o mês da coorte (0 = mês base). */
  months_since: z.number(),
  activity_month: z.string(),
  active_households: z.number(),
  retention_rate: z.number(),
});

export const cohortSchema = z.object({
  /** Mês da PRIMEIRA aparição na janela (não aquisição real — ver left-censoring). */
  cohort_month: z.string(),
  cohort_size: z.number(),
  /** Nº de pontos VARIÁVEL por coorte (coortes tardias maturam menos). */
  points: z.array(cohortPointSchema),
});

export const retentionCohortsSchema = z.object({
  as_of_date: z.string(),
  n_cohorts: z.number(),
  cohorts: z.array(cohortSchema),
  note: z.string(),
});

// ---------------------------------------------------------------------------
// Campanhas (espelha GET /campaigns/performance, /by-type e /overlap)
// Página deliberadamente NÃO-monetária: os dados não permitem atribuir
// receita a campanha (transactions.coupon_disc não traz coupon_upc).
// ---------------------------------------------------------------------------

/** Tipos reais de campanha no dataset (rótulos opacos A/B/C). */
export const CAMPAIGN_TYPES = ["Type A", "Type B", "Type C"] as const;
export type CampaignType = (typeof CAMPAIGN_TYPES)[number];

export const campaignPerformanceRowSchema = z.object({
  campaign_id: z.string(),
  campaign_type: z.string(),
  /** ISO "YYYY-MM-DD". */
  start_date: z.string(),
  end_date: z.string(),
  households_exposed: z.number(),
  households_redeemed: z.number(),
  /** Fração 0..1 = resgataram / expostos (binária por domicílio). */
  redemption_rate: z.number(),
});

export const campaignPerformanceSchema = z.object({
  as_of_date: z.string(),
  n_campaigns: z.number(),
  universe_households: z.number(),
  /** Domicílios DISTINTOS alcançados por ≥1 campanha (NÃO é soma dos expostos). */
  households_exposed_total: z.number(),
  campaigns: z.array(campaignPerformanceRowSchema),
  note: z.string(),
});

export const campaignTypeRowSchema = z.object({
  campaign_type: z.string(),
  n_campaigns: z.number(),
  households_exposed: z.number(),
  /** Único campo ADITIVO entre tipos. */
  n_redemption_events: z.number(),
  households_redeemed: z.number(),
  n_coupons_redeemed: z.number(),
  redemption_rate: z.number(),
});

export const campaignsByTypeSchema = z.object({
  as_of_date: z.string(),
  types: z.array(campaignTypeRowSchema),
  note: z.string(),
});

export const campaignOverlapPointSchema = z.object({
  n_campaigns_exposed: z.number(),
  n_households: z.number(),
});

export const campaignOverlapSchema = z.object({
  as_of_date: z.string(),
  total_exposed: z.number(),
  universe: z.number(),
  /** Fração 0..1 = total_exposed / universe. */
  exposure_rate: z.number(),
  avg_campaigns_per_household: z.number(),
  max_campaigns_per_household: z.number(),
  distribution: z.array(campaignOverlapPointSchema),
  note: z.string(),
});

export type Health = z.infer<typeof healthSchema>;
export type Meta = z.infer<typeof metaSchema>;
export type Overview = z.infer<typeof overviewSchema>;
export type WeeklyRevenuePoint = z.infer<typeof weeklyRevenuePointSchema>;
export type WeeklyRevenue = z.infer<typeof weeklyRevenueSchema>;
export type RfmSegment = z.infer<typeof rfmSegmentSchema>;
export type RfmSegments = z.infer<typeof rfmSegmentsSchema>;
export type RfmHousehold = z.infer<typeof rfmHouseholdSchema>;
export type RfmHouseholds = z.infer<typeof rfmHouseholdsSchema>;
export type RetentionMonthlyPoint = z.infer<typeof retentionMonthlyPointSchema>;
export type RetentionMonthly = z.infer<typeof retentionMonthlySchema>;
export type CohortPoint = z.infer<typeof cohortPointSchema>;
export type Cohort = z.infer<typeof cohortSchema>;
export type RetentionCohorts = z.infer<typeof retentionCohortsSchema>;
export type CampaignPerformanceRow = z.infer<
  typeof campaignPerformanceRowSchema
>;
export type CampaignPerformance = z.infer<typeof campaignPerformanceSchema>;
export type CampaignTypeRow = z.infer<typeof campaignTypeRowSchema>;
export type CampaignsByType = z.infer<typeof campaignsByTypeSchema>;
export type CampaignOverlapPoint = z.infer<typeof campaignOverlapPointSchema>;
export type CampaignOverlap = z.infer<typeof campaignOverlapSchema>;

/** Colunas ordenáveis da tabela de campanhas (ordenação client-side). */
export const CAMPAIGN_SORT_FIELDS = [
  "households_exposed",
  "households_redeemed",
  "redemption_rate",
] as const;
export type CampaignSortField = (typeof CAMPAIGN_SORT_FIELDS)[number];

/** Parâmetros aceitos por GET /rfm/households (todos opcionais). */
export interface RfmHouseholdsParams {
  segment?: RfmSegmentName;
  sortBy?: RfmSortField;
  order?: SortOrder;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// Erros tipados
// ---------------------------------------------------------------------------

/** O snapshot ainda não foi publicado pelo Dagster (HTTP 503). */
export class SnapshotUnavailableError extends Error {
  readonly kind = "snapshot_unavailable" as const;
  constructor(message = "Snapshot indisponível.") {
    super(message);
    this.name = "SnapshotUnavailableError";
  }
}

/** Qualquer outra falha de rede/HTTP/parse. */
export class ApiError extends Error {
  readonly kind = "api_error" as const;
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Narrowing: a UI usa isto para decidir a mensagem de erro. */
export function isSnapshotUnavailable(
  error: unknown,
): error is SnapshotUnavailableError {
  return error instanceof SnapshotUnavailableError;
}

// ---------------------------------------------------------------------------
// Fetch + validação
// ---------------------------------------------------------------------------

async function request<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ApiError(
      `Falha de rede ao acessar ${path}. A API está no ar em ${BASE_URL}?`,
    );
  }

  if (response.status === 503) {
    let detail = "Snapshot indisponível. Publique um snapshot via Dagster.";
    try {
      const body: unknown = await response.json();
      if (
        body &&
        typeof body === "object" &&
        "detail" in body &&
        typeof (body as { detail: unknown }).detail === "string"
      ) {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      /* mantém a mensagem padrão */
    }
    throw new SnapshotUnavailableError(detail);
  }

  if (!response.ok) {
    throw new ApiError(
      `A API respondeu ${response.status} em ${path}.`,
      response.status,
    );
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(`Resposta não-JSON em ${path}.`, response.status);
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError(
      `Contrato inesperado em ${path}: ${parsed.error.issues
        .map((i) => i.path.join("."))
        .join(", ")}.`,
    );
  }
  return parsed.data;
}

/** Monta a query string de /rfm/households, omitindo o que estiver indefinido. */
function buildRfmHouseholdsQuery(params: RfmHouseholdsParams): string {
  const search = new URLSearchParams();
  if (params.segment) search.set("segment", params.segment);
  if (params.sortBy) search.set("sort_by", params.sortBy);
  if (params.order) search.set("order", params.order);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  getHealth: () => request("/health", healthSchema),
  getMeta: () => request("/meta", metaSchema),
  getOverview: () => request("/overview", overviewSchema),
  getRevenueWeekly: () => request("/revenue/weekly", weeklyRevenueSchema),
  getRfmSegments: () => request("/rfm/segments", rfmSegmentsSchema),
  getRfmHouseholds: (params: RfmHouseholdsParams = {}) =>
    request(
      `/rfm/households${buildRfmHouseholdsQuery(params)}`,
      rfmHouseholdsSchema,
    ),
  getRetentionMonthly: () =>
    request("/retention/monthly", retentionMonthlySchema),
  getRetentionCohorts: () =>
    request("/retention/cohorts", retentionCohortsSchema),
  getCampaignPerformance: () =>
    request("/campaigns/performance", campaignPerformanceSchema),
  getCampaignsByType: () => request("/campaigns/by-type", campaignsByTypeSchema),
  getCampaignOverlap: () => request("/campaigns/overlap", campaignOverlapSchema),
};
