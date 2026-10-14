"""GET /rfm/segments — distribuição dos segmentos RFM."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import services
from ..config import Settings, get_settings
from ..deps import get_snapshot
from ..schemas import RfmSegmentsResponse
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
