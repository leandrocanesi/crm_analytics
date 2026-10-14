"""Customer Intelligence Lab — pipeline Dagster (Bronze, Silver, Gold, Snapshot).

Define o code location: um asset Bronze (ingestão fiel), um asset Silver
(tipagem/limpeza/integridade), os assets Gold (visões analíticas) e o asset
Snapshot (publicação atômica do .duckdb read-only que a API consome), com asset
checks embutidos e dependência explícita bronze → silver → gold → snapshot.
Descoberta via ``dagster dev -m crm_pipelines`` ou
``dagster asset materialize -m crm_pipelines --select "*"``.
"""

from __future__ import annotations

from dagster import Definitions

from .bronze import build_bronze_asset
from .config import TABLE_SPECS
from .gold import build_gold_asset
from .gold_config import GOLD_SPECS
from .silver import build_silver_asset
from .silver_config import SILVER_SPECS
from .snapshot import build_published_snapshot_asset

bronze_assets = [build_bronze_asset(spec) for spec in TABLE_SPECS]
silver_assets = [build_silver_asset(spec) for spec in SILVER_SPECS]
gold_assets = [build_gold_asset(spec) for spec in GOLD_SPECS]
snapshot_assets = [build_published_snapshot_asset()]

defs = Definitions(
    assets=[*bronze_assets, *silver_assets, *gold_assets, *snapshot_assets]
)

__all__ = [
    "defs",
    "bronze_assets",
    "silver_assets",
    "gold_assets",
    "snapshot_assets",
]
