import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, type RfmHouseholdsParams } from "@/lib/api";

/**
 * Chaves de query estáveis e centralizadas.
 * Dados do snapshot são imutáveis até uma nova publicação, então usamos
 * staleTime longo — não faz sentido refazer fetch de métricas históricas.
 */
export const queryKeys = {
  health: ["health"] as const,
  meta: ["meta"] as const,
  overview: ["overview"] as const,
  revenueWeekly: ["revenue", "weekly"] as const,
  rfmSegments: ["rfm", "segments"] as const,
  /** Inclui os params normalizados para refazer fetch ao mudar filtro/ordenação/página. */
  rfmHouseholds: (params: RfmHouseholdsParams) =>
    ["rfm", "households", params] as const,
  retentionMonthly: ["retention", "monthly"] as const,
  retentionCohorts: ["retention", "cohorts"] as const,
  campaignPerformance: ["campaigns", "performance"] as const,
  campaignsByType: ["campaigns", "by-type"] as const,
  campaignOverlap: ["campaigns", "overlap"] as const,
};

/** Snapshot é imutável; 5 min de staleTime evita refetch desnecessário. */
const SNAPSHOT_STALE_TIME = 5 * 60 * 1000;

export function useMeta() {
  return useQuery({
    queryKey: queryKeys.meta,
    queryFn: api.getMeta,
    staleTime: SNAPSHOT_STALE_TIME,
  });
}

export function useOverview() {
  return useQuery({
    queryKey: queryKeys.overview,
    queryFn: api.getOverview,
    staleTime: SNAPSHOT_STALE_TIME,
  });
}

export function useRevenueWeekly() {
  return useQuery({
    queryKey: queryKeys.revenueWeekly,
    queryFn: api.getRevenueWeekly,
    staleTime: SNAPSHOT_STALE_TIME,
  });
}

export function useRfmSegments() {
  return useQuery({
    queryKey: queryKeys.rfmSegments,
    queryFn: api.getRfmSegments,
    staleTime: SNAPSHOT_STALE_TIME,
  });
}

/**
 * Domicílios RFM com filtro/ordenação/paginação server-side.
 * `placeholderData: keepPreviousData` mantém a página anterior visível
 * durante o refetch, evitando que a tabela pisque ao paginar/ordenar.
 */
export function useRfmHouseholds(params: RfmHouseholdsParams) {
  return useQuery({
    queryKey: queryKeys.rfmHouseholds(params),
    queryFn: () => api.getRfmHouseholds(params),
    staleTime: SNAPSHOT_STALE_TIME,
    placeholderData: keepPreviousData,
  });
}

export function useRetentionMonthly() {
  return useQuery({
    queryKey: queryKeys.retentionMonthly,
    queryFn: api.getRetentionMonthly,
    staleTime: SNAPSHOT_STALE_TIME,
  });
}

export function useRetentionCohorts() {
  return useQuery({
    queryKey: queryKeys.retentionCohorts,
    queryFn: api.getRetentionCohorts,
    staleTime: SNAPSHOT_STALE_TIME,
  });
}

export function useCampaignPerformance() {
  return useQuery({
    queryKey: queryKeys.campaignPerformance,
    queryFn: api.getCampaignPerformance,
    staleTime: SNAPSHOT_STALE_TIME,
  });
}

export function useCampaignsByType() {
  return useQuery({
    queryKey: queryKeys.campaignsByType,
    queryFn: api.getCampaignsByType,
    staleTime: SNAPSHOT_STALE_TIME,
  });
}

export function useCampaignOverlap() {
  return useQuery({
    queryKey: queryKeys.campaignOverlap,
    queryFn: api.getCampaignOverlap,
    staleTime: SNAPSHOT_STALE_TIME,
  });
}
