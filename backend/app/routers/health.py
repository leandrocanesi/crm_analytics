"""GET /health — a API está no ar e enxerga um snapshot válido?"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_snapshot
from ..schemas import HealthResponse
from ..snapshot import SnapshotManager, SnapshotUnavailableError

router = APIRouter(tags=["infra"])


@router.get("/health", response_model=HealthResponse, summary="Healthcheck")
def health(snap: SnapshotManager = Depends(get_snapshot)) -> HealthResponse:
    """Sempre 200 se a API respondeu. Reporta se o snapshot está disponível.

    Não falha quando não há snapshot — isso é informado no corpo (para o
    frontend/monitoramento decidir), enquanto os endpoints de dados retornam 503.
    """
    try:
        pointer = snap.pointer()
        return HealthResponse(
            status="ok",
            snapshot_available=True,
            snapshot_version=pointer.get("version"),
            schema_version=pointer.get("schema_version"),
        )
    except SnapshotUnavailableError:
        return HealthResponse(status="ok", snapshot_available=False)
