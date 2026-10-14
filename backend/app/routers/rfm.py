"""GET /rfm/segments — distribuição dos segmentos RFM.
GET /rfm/households — RFM por domicílio (paginado/ordenado/filtrado)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .. import services
from ..config import Settings, get_settings
from ..deps import get_snapshot
from ..schemas import (
    RfmHouseholdsResponse,
    RfmSegmentName,
    RfmSegmentsResponse,
    RfmSortBy,
    SortOrder,
)
from ..snapshot import SnapshotManager

router = APIRouter(prefix="/rfm", tags=["overview"])


@router.get(
    "/segments",
    response_model=RfmSegmentsResponse,
    summary="Distribuição dos segmentos RFM",
)
def rfm_segments(
    snap: SnapshotManager = Depends(get_snapshot),
    settings: Settings = Depends(get_settings),
) -> RfmSegmentsResponse:
    return services.build_rfm_segments(snap, settings)


@router.get(
    "/households",
    response_model=RfmHouseholdsResponse,
    summary="RFM por domicílio (detalhado, paginado)",
)
def rfm_households(  # noqa: PLR0913, PLR0917 — query params do FastAPI na assinatura.
    segment: RfmSegmentName | None = Query(
        default=None,
        description="Filtra por um dos 7 segmentos RFM exatos. None = todos.",
    ),
    sort_by: RfmSortBy = Query(
        default=RfmSortBy.MONETARY_VALUE,
        description="Coluna de ordenação (allow-list).",
    ),
    order: SortOrder = Query(
        default=SortOrder.DESC, description="Direção da ordenação (asc|desc)."
    ),
    limit: int = Query(
        default=50, ge=1, le=200, description="Tamanho de página (1..200; >200 → 422)."
    ),
    offset: int = Query(default=0, ge=0, description="Deslocamento de paginação (>= 0)."),
    snap: SnapshotManager = Depends(get_snapshot),
    settings: Settings = Depends(get_settings),
) -> RfmHouseholdsResponse:
    return services.build_rfm_households(
        snap,
        settings,
        segment=segment.value if segment is not None else None,
        sort_by=sort_by,
        order=order,
        limit=limit,
        offset=offset,
    )
