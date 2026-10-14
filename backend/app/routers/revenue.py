"""GET /revenue/weekly — série temporal de receita semanal."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import services
from ..config import Settings, get_settings
from ..deps import get_snapshot
from ..schemas import WeeklyRevenueResponse
from ..snapshot import SnapshotManager

router = APIRouter(prefix="/revenue", tags=["overview"])


@router.get(
    "/weekly",
    response_model=WeeklyRevenueResponse,
    summary="Receita observada por semana",
)
def weekly_revenue(
    snap: SnapshotManager = Depends(get_snapshot),
    settings: Settings = Depends(get_settings),
) -> WeeklyRevenueResponse:
    return services.build_weekly_revenue(snap, settings)
