"""GET /overview — cards do topo do Overview."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import services
from ..config import Settings, get_settings
from ..deps import get_snapshot
from ..schemas import OverviewResponse
from ..snapshot import SnapshotManager

router = APIRouter(tags=["overview"])


@router.get("/overview", response_model=OverviewResponse, summary="Cards do Overview")
def overview(
    snap: SnapshotManager = Depends(get_snapshot),
    settings: Settings = Depends(get_settings),
) -> OverviewResponse:
    return services.build_overview(snap, settings)
