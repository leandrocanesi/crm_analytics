import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

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
