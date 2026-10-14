"""Lógica de analytics (orquestra consultas → monta contratos de resposta).

As definições de métrica vivem em ``docs/metrics.md`` e já estão materializadas no
Gold; aqui só expomos o que o snapshot traz. A única aritmética feita aqui é
derivação trivial e consistente com o Gold: ticket médio = receita/cestas, e as
frações (share) dos segmentos. Nada é recalculado a partir do grão de linha.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .config import Settings
from .queries import META, OVERVIEW, RFM_SEGMENTS, WEEKLY_REVENUE
from .schemas import (
    MetaResponse,
    OverviewResponse,
    RfmSegment,
    RfmSegmentsResponse,
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
