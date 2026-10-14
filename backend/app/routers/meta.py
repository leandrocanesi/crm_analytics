"""GET /meta — metadados do snapshot ativo (proveniência + âncoras)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import services
from ..config import Settings, get_settings
from ..deps import get_snapshot
from ..schemas import MetaResponse
from ..snapshot import SnapshotManager

router = APIRouter(tags=["infra"])


@router.get("/meta", response_model=MetaResponse, summary="Metadados do snapshot")
def meta(
    snap: SnapshotManager = Depends(get_snapshot),
    settings: Settings = Depends(get_settings),
) -> MetaResponse:
    return services.build_meta(snap, settings)
