"""Lógica de analytics (orquestra consultas → monta contratos de resposta).

As definições de métrica vivem em ``docs/metrics.md`` e já estão materializadas no
Gold; aqui só expomos o que o snapshot traz. A única aritmética feita aqui é
derivação trivial e consistente com o Gold: ticket médio = receita/cestas, e as
frações (share) dos segmentos. Nada é recalculado a partir do grão de linha.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from .config import Settings
from .queries import (
    CAMPAIGN_BY_TYPE,
    CAMPAIGN_EXPOSED_TOTAL,
    CAMPAIGN_OVERLAP_DISTRIBUTION,
    CAMPAIGN_OVERLAP_SUMMARY,
    CAMPAIGN_PERFORMANCE,
    COHORT_RETENTION,
    META,
    OVERVIEW,
    RETENTION_MONTHLY,
    RFM_HOUSEHOLDS,
    RFM_HOUSEHOLDS_COUNT,
    RFM_SEGMENTS,
    RFM_SORT_COLUMNS,
    RFM_SORT_ORDERS,
    WEEKLY_REVENUE,
)
from .schemas import (
    CampaignByTypeResponse,
    CampaignOverlapBin,
    CampaignOverlapResponse,
    CampaignPerformanceItem,
    CampaignPerformanceResponse,
    CampaignTypeItem,
    CohortRetention,
    CohortRetentionPoint,
    MetaResponse,
    OverviewResponse,
    RetentionCohortsResponse,
    RetentionMonthlyPoint,
    RetentionMonthlyResponse,
    RfmHousehold,
    RfmHouseholdsResponse,
    RfmSegment,
    RfmSegmentsResponse,
    RfmSortBy,
    SortOrder,
    WeeklyRevenuePoint,
    WeeklyRevenueResponse,
)
from .snapshot import SnapshotManager


def _f(value: Any) -> float:
    """Converte Decimal/None para float (valores monetários do DuckDB são Decimal)."""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _money(value: Any) -> float:
    """Float monetário arredondado a 2 casas (centavos)."""
    return round(_f(value), 2)


def _isodate(value: Any) -> str:
    """Converte DATE do DuckDB (``datetime.date``) para string ISO 'YYYY-MM-DD'."""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()[:10]
    # Fallback defensivo: já veio como string ISO.
    return str(value)[:10]


def _rate(value: Any) -> float:
    """Taxa de retenção em [0,1], arredondada a 4 casas (o Gold já garante o range)."""
    return round(_f(value), 4)


def build_meta(snap: SnapshotManager, settings: Settings) -> MetaResponse:
    row = snap.query_one(META)
    pointer = snap.pointer()
    return MetaResponse(
        schema_version=str(row["schema_version"]),
        snapshot_version=str(row["snapshot_version"]),
        built_at=str(row["built_at"]),
        published_at=pointer.get("published_at"),
        as_of_date=settings.as_of_date,
        revenue_total=_money(row["revenue_total"]),
        basket_count=int(row["basket_count"]),
        household_count=int(row["household_count"]),
        currency=settings.currency,
        git_commit=str(row["git_commit"]),
        content_hash=str(row["content_hash"]),
        tables=list(pointer.get("tables", [])),
    )


def build_overview(snap: SnapshotManager, settings: Settings) -> OverviewResponse:
    row = snap.query_one(OVERVIEW)
    total_revenue = _money(row["total_revenue"])
    n_baskets = int(row["n_baskets"])
    avg_basket = round(total_revenue / n_baskets, 2) if n_baskets else 0.0
    n_active = int(row["n_active_households"])
    return OverviewResponse(
        total_revenue=total_revenue,
        n_active_households=n_active,
        # No período completo, ativos distintos == universo (todos compraram >=1 vez).
        household_universe=n_active,
        n_baskets=n_baskets,
        avg_basket_value=avg_basket,
        as_of_date=settings.as_of_date,
        currency=settings.currency,
    )


def build_weekly_revenue(
    snap: SnapshotManager, settings: Settings
) -> WeeklyRevenueResponse:
    rows = snap.query(WEEKLY_REVENUE)
    series: list[WeeklyRevenuePoint] = []
    total = 0.0
    for r in rows:
        revenue = _money(r["revenue"])
        n_baskets = int(r["n_baskets"])
        total += revenue
        series.append(
            WeeklyRevenuePoint(
                week=int(r["week"]),
                revenue=revenue,
                n_baskets=n_baskets,
                n_active_households=int(r["n_active_households"]),
                avg_basket_value=round(revenue / n_baskets, 2) if n_baskets else 0.0,
            )
        )
    return WeeklyRevenueResponse(
        as_of_date=settings.as_of_date,
        currency=settings.currency,
        n_weeks=len(series),
        total_revenue=round(total, 2),
        series=series,
    )


def build_rfm_segments(
    snap: SnapshotManager, settings: Settings
) -> RfmSegmentsResponse:
    rows = snap.query(RFM_SEGMENTS)
    total_hh = sum(int(r["n_households"]) for r in rows)
    total_monetary = sum(_f(r["monetary_value"]) for r in rows)
    segments: list[RfmSegment] = []
    for r in rows:
        n_hh = int(r["n_households"])
        monetary = _money(r["monetary_value"])
        segments.append(
            RfmSegment(
                segment=str(r["segment"]),
                n_households=n_hh,
                household_share=round(n_hh / total_hh, 4) if total_hh else 0.0,
                monetary_value=monetary,
                monetary_share=(
                    round(_f(r["monetary_value"]) / total_monetary, 4)
                    if total_monetary
                    else 0.0
                ),
            )
        )
    return RfmSegmentsResponse(
        as_of_date=settings.as_of_date,
        currency=settings.currency,
        n_segments=len(segments),
        n_households_total=total_hh,
        segments=segments,
    )


def build_rfm_households(  # noqa: PLR0913 — filtro + paginação + ordenação (kw-only).
    snap: SnapshotManager,
    settings: Settings,
    *,
    segment: str | None,
    sort_by: RfmSortBy,
    order: SortOrder,
    limit: int,
    offset: int,
) -> RfmHouseholdsResponse:
    """RFM por domicílio, paginado/ordenado/filtrado.

    ``segment`` já vem validado pela allow-list (enum do router) ou None.
    ``sort_by``/``order`` são enums → resolvidos nos mapas allow-list; só assim
    entram no ORDER BY (nunca string crua do cliente — CLAUDE.md regra 7).
    """
    # ORDER BY montado APENAS a partir das allow-lists (chaves = valores do enum).
    sql = RFM_HOUSEHOLDS.format(
        order_by=RFM_SORT_COLUMNS[sort_by.value],
        order=RFM_SORT_ORDERS[order.value],
    )
    # Filtro, limit e offset entram por bind (?), jamais concatenados.
    rows = snap.query(sql, [segment, segment, limit, offset])
    total = int(snap.query_one(RFM_HOUSEHOLDS_COUNT, [segment, segment])["total"])

    households = [
        RfmHousehold(
            household_id=int(r["household_id"]),
            recency_days=int(r["recency_days"]),
            frequency_baskets=int(r["frequency_baskets"]),
            monetary_value=_money(r["monetary_value"]),
            r_score=int(r["r_score"]),
            f_score=int(r["f_score"]),
            m_score=int(r["m_score"]),
            rfm_segment=str(r["rfm_segment"]),
        )
        for r in rows
    ]
    return RfmHouseholdsResponse(
        as_of_date=settings.as_of_date,
        currency=settings.currency,
        total=total,
        limit=limit,
        offset=offset,
        segment=segment,
        households=households,
    )


def build_retention_monthly(
    snap: SnapshotManager, settings: Settings
) -> RetentionMonthlyResponse:
    """Série mensal de retenção período-a-período (metrics.md §6.2).

    Só expõe o que o Gold já calculou (``agg_retention_monthly``); nada é
    recalculado aqui. A query já vem ordenada por ``activity_month`` ASC.
    """
    rows = snap.query(RETENTION_MONTHLY)
    series = [
        RetentionMonthlyPoint(
            activity_month=_isodate(r["activity_month"]),
            active_households=int(r["active_households"]),
            retained_next_month=int(r["retained_next_month"]),
            retention_rate=_rate(r["retention_rate"]),
            next_month_partial=bool(r["next_month_partial"]),
        )
        for r in rows
    ]
    return RetentionMonthlyResponse(
        as_of_date=settings.as_of_date,
        n_months=len(series),
        series=series,
    )


def build_retention_cohorts(
    snap: SnapshotManager, settings: Settings
) -> RetentionCohortsResponse:
    """Triângulo de coortes de retenção (metrics.md §6.3).

    A query traz 84 linhas (coorte × mês) já ordenadas por ``cohort_month`` ASC e
    ``months_since`` ASC; aqui só montamos a estrutura aninhada por coorte. Cada
    coorte aparece uma vez (ordem de primeira ocorrência = ordem da query).
    """
    rows = snap.query(COHORT_RETENTION)
    cohorts: list[CohortRetention] = []
    by_month: dict[str, CohortRetention] = {}
    for r in rows:
        cohort_key = _isodate(r["cohort_month"])
        cohort = by_month.get(cohort_key)
        if cohort is None:
            cohort = CohortRetention(
                cohort_month=cohort_key,
                cohort_size=int(r["cohort_size"]),
                points=[],
            )
            by_month[cohort_key] = cohort
            cohorts.append(cohort)
        cohort.points.append(
            CohortRetentionPoint(
                months_since=int(r["months_since"]),
                activity_month=_isodate(r["activity_month"]),
                active_households=int(r["active_households"]),
                retention_rate=_rate(r["retention_rate"]),
            )
        )
    return RetentionCohortsResponse(
        as_of_date=settings.as_of_date,
        n_cohorts=len(cohorts),
        cohorts=cohorts,
    )


# --- Campanha e Cupom (metrics.md §8, factual 8.1–8.4) -------------------------
# Só expõe o que o Gold já calculou (agg_campaign_performance, agg_coupon_redemption,
# agg_household_campaign_exposure, dim_campaign, bridge_household_campaign). Nenhuma
# métrica monetária: os dados não ligam receita a campanha (metrics.md §8.0).


def build_campaign_performance(
    snap: SnapshotManager, settings: Settings
) -> CampaignPerformanceResponse:
    """Alcance + taxa de resposta por campanha (metrics.md §8.1 e §8.2.a).

    households_exposed_total é o universo DISTINTO alcançado (de
    bridge_household_campaign) — NÃO a soma por campanha (alcance não é aditivo,
    §8.0.2). universe_households reconcilia a âncora do painel (household_count).
    """
    rows = snap.query(CAMPAIGN_PERFORMANCE)
    exposed_total = int(
        snap.query_one(CAMPAIGN_EXPOSED_TOTAL)["households_exposed_total"]
    )
    universe = int(snap.query_one(META)["household_count"])
    campaigns = [
        CampaignPerformanceItem(
            campaign_id=str(r["campaign_id"]),
            campaign_type=str(r["campaign_type"]),
            start_date=_isodate(r["start_date"]),
            end_date=_isodate(r["end_date"]),
            households_exposed=int(r["households_exposed"]),
            households_redeemed=int(r["households_redeemed"]),
            redemption_rate=_rate(r["redemption_rate"]),
        )
        for r in rows
    ]
    return CampaignPerformanceResponse(
        as_of_date=settings.as_of_date,
        n_campaigns=len(campaigns),
        universe_households=universe,
        households_exposed_total=exposed_total,
        campaigns=campaigns,
    )


def build_campaign_by_type(
    snap: SnapshotManager, settings: Settings
) -> CampaignByTypeResponse:
    """Resgate agregado por tipo A/B/C (metrics.md §8.4).

    Expostos/resgatadores NÃO são aditivos entre tipos; só n_redemption_events soma
    (a ressalva vive no ``note`` do schema).
    """
    rows = snap.query(CAMPAIGN_BY_TYPE)
    types = [
        CampaignTypeItem(
            campaign_type=str(r["campaign_type"]),
            n_campaigns=int(r["n_campaigns"]),
            households_exposed=int(r["households_exposed"]),
            n_redemption_events=int(r["n_redemption_events"]),
            households_redeemed=int(r["households_redeemed"]),
            n_coupons_redeemed=int(r["n_coupons_redeemed"]),
            redemption_rate=_rate(r["redemption_rate"]),
        )
        for r in rows
    ]
    return CampaignByTypeResponse(
        as_of_date=settings.as_of_date,
        types=types,
    )


def build_campaign_overlap(
    snap: SnapshotManager, settings: Settings
) -> CampaignOverlapResponse:
    """Participação e sobreposição de campanha no painel (metrics.md §8.3).

    exposure_rate = total_exposed / universo do painel (household_count, âncora).
    A distribuição é o histograma de nº de campanhas por domicílio (soma =
    total_exposed).
    """
    summary = snap.query_one(CAMPAIGN_OVERLAP_SUMMARY)
    total_exposed = int(summary["total_exposed"])
    universe = int(snap.query_one(META)["household_count"])
    rows = snap.query(CAMPAIGN_OVERLAP_DISTRIBUTION)
    distribution = [
        CampaignOverlapBin(
            n_campaigns_exposed=int(r["n_campaigns_exposed"]),
            n_households=int(r["n_households"]),
        )
        for r in rows
    ]
    return CampaignOverlapResponse(
        as_of_date=settings.as_of_date,
        total_exposed=total_exposed,
        universe=universe,
        exposure_rate=round(total_exposed / universe, 4) if universe else 0.0,
        avg_campaigns_per_household=round(
            _f(summary["avg_campaigns_per_household"]), 2
        ),
        max_campaigns_per_household=int(summary["max_campaigns_per_household"]),
        distribution=distribution,
    )
