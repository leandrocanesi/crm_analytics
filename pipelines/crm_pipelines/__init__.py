"""Customer Intelligence Lab — pipeline Dagster (camadas Bronze e Silver).

Define o code location: um asset Bronze (ingestão fiel) e um asset Silver
(tipagem/limpeza/integridade) por tabela, com asset checks embutidos e
dependência explícita bronze → silver. Descoberta via
``dagster dev -m crm_pipelines`` ou
``dagster asset materialize -m crm_pipelines --select "*"``.
"""

from __future__ import annotations

from dagster import Definitions

from .bronze import build_bronze_asset
from .config import TABLE_SPECS
from .silver import build_silver_asset
from .silver_config import SILVER_SPECS

bronze_assets = [build_bronze_asset(spec) for spec in TABLE_SPECS]
silver_assets = [build_silver_asset(spec) for spec in SILVER_SPECS]

defs = Definitions(assets=[*bronze_assets, *silver_assets])

__all__ = ["defs", "bronze_assets", "silver_assets"]
