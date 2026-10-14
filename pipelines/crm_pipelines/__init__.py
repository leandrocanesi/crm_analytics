"""Customer Intelligence Lab — pipeline Dagster (camada Bronze).

Define o code location: um asset Bronze por tabela de origem, com asset checks
embutidos. Descoberta via ``dagster dev -m crm_pipelines`` ou
``dagster asset materialize -m crm_pipelines --select "*"``.
"""

from __future__ import annotations

from dagster import Definitions

from .bronze import build_bronze_asset
from .config import TABLE_SPECS

bronze_assets = [build_bronze_asset(spec) for spec in TABLE_SPECS]

defs = Definitions(assets=bronze_assets)

__all__ = ["defs", "bronze_assets"]
