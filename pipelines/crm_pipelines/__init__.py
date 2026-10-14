"""Customer Intelligence Lab — pipeline Dagster (camadas Bronze, Silver e Gold).

Define o code location: um asset Bronze (ingestão fiel), um asset Silver
(tipagem/limpeza/integridade) e os assets Gold (visões analíticas prontas para a
API), com asset checks embutidos e dependência explícita bronze → silver → gold.
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

bronze_assets = [build_bronze_asset(spec) for spec in TABLE_SPECS]
silver_assets = [build_silver_asset(spec) for spec in SILVER_SPECS]
gold_assets = [build_gold_asset(spec) for spec in GOLD_SPECS]

defs = Definitions(assets=[*bronze_assets, *silver_assets, *gold_assets])

__all__ = ["defs", "bronze_assets", "silver_assets", "gold_assets"]
