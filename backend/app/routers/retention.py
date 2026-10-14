"""GET /retention/monthly — retenção mensal período-a-período (metrics.md §6.2).
GET /retention/cohorts — triângulo de coortes de retenção (metrics.md §6.3).

Ambos são SELECT fixos e ordenados, sem parâmetros do cliente (CLAUDE.md regra 7).
Leitura OBSERVACIONAL: correlação ≠ causalidade (regra 9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import services
from ..config import Settings, get_settings
from ..deps import get_snapshot
from ..schemas import RetentionCohortsResponse, RetentionMonthlyResponse
from ..snapshot import SnapshotManager

router = APIRouter(prefix="/retention", tags=["retention"])


@router.get(
    "/monthly",
    response_model=RetentionMonthlyResponse,
    summary="Retenção mensal período-a-período",
)
def retention_monthly(
    snap: SnapshotManager = Depends(get_snapshot),
    settings: Settings = Depends(get_settings),
) -> RetentionMonthlyResponse:
    return services.build_retention_monthly(snap, settings)


@router.get(
    "/cohorts",
    response_model=RetentionCohortsResponse,
    summary="Triângulo de coortes de retenção",
)
def retention_cohorts(
    snap: SnapshotManager = Depends(get_snapshot),
    settings: Settings = Depends(get_settings),
) -> RetentionCohortsResponse:
    return services.build_retention_cohorts(snap, settings)
