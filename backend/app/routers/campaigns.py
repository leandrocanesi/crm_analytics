"""GET /campaigns/performance — alcance + taxa de resgate por campanha (§8.1/§8.2).
GET /campaigns/by-type — resgate agregado por tipo A/B/C (metrics.md §8.4).
GET /campaigns/overlap — participação e sobreposição no painel (metrics.md §8.3).

Todos são SELECT fixos e ordenados, sem parâmetros do cliente (CLAUDE.md regra 7).
Leitura FACTUAL/OBSERVACIONAL: exposição ≠ efeito, resgate ≠ conversão causada, e
NENHUMA métrica monetária (os dados não ligam receita a campanha — metrics.md §8.0).
Correlação ≠ causalidade (regra 9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import services
from ..config import Settings, get_settings
from ..deps import get_snapshot
from ..schemas import (
    CampaignByTypeResponse,
    CampaignOverlapResponse,
    CampaignPerformanceResponse,
)
from ..snapshot import SnapshotManager

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get(
    "/performance",
    response_model=CampaignPerformanceResponse,
    summary="Alcance e taxa de resgate por campanha",
)
def campaign_performance(
    snap: SnapshotManager = Depends(get_snapshot),
    settings: Settings = Depends(get_settings),
) -> CampaignPerformanceResponse:
    return services.build_campaign_performance(snap, settings)


@router.get(
    "/by-type",
    response_model=CampaignByTypeResponse,
    summary="Resgate agregado por tipo de campanha (A/B/C)",
)
def campaign_by_type(
    snap: SnapshotManager = Depends(get_snapshot),
    settings: Settings = Depends(get_settings),
) -> CampaignByTypeResponse:
    return services.build_campaign_by_type(snap, settings)


@router.get(
    "/overlap",
    response_model=CampaignOverlapResponse,
    summary="Participação e sobreposição de campanha no painel",
)
def campaign_overlap(
    snap: SnapshotManager = Depends(get_snapshot),
    settings: Settings = Depends(get_settings),
) -> CampaignOverlapResponse:
    return services.build_campaign_overlap(snap, settings)
