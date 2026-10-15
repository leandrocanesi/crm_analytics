"""Configuração estática da camada Bronze.

Centraliza caminhos, a especificação de cada tabela de origem (nome do arquivo
``.rds``/``.rda``, colunas de ID, chave de particionamento, contagem esperada de
linhas) e constantes de validação (teste-âncora de receita).

Tudo aqui é determinístico — não há leitura de relógio nem de estado externo —
para manter a ingestão reprodutível.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos do repositório (resolvidos a partir deste arquivo, sem depender do
# diretório de trabalho — importante porque threads/CLI podem mudar o cwd).
# ---------------------------------------------------------------------------
# config.py -> crm_pipelines -> pipelines -> raiz do monorepo
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
RAW_DIR: Path = REPO_ROOT / "data" / "raw" / "completejourney"
BRONZE_DIR: Path = REPO_ROOT / "data" / "processed" / "bronze"
SILVER_DIR: Path = REPO_ROOT / "data" / "processed" / "silver"
GOLD_DIR: Path = REPO_ROOT / "data" / "processed" / "gold"
SHA256SUMS_FILE: Path = RAW_DIR / "SHA256SUMS.txt"

# ---------------------------------------------------------------------------
# Constantes de validação (ver docs/data-model.md §3 e §4).
# Receita observada = SUM(transactions.sales_value) no grão item-de-linha.
# ---------------------------------------------------------------------------
REVENUE_ANCHOR_USD: float = 4_596_039.58
# Tolerância do teste-âncora de receita. Os valores são monetários com 2 casas;
# 0,01 absorve ruído de ponto flutuante na soma de ~1,47M linhas sem mascarar
# qualquer fan-out (que erraria por milhares de dólares).
REVENUE_ANCHOR_TOL_USD: float = 0.01

# Âncoras de contagem (grão da fato e agregados), ver docs/metrics.md §0.
BASKET_ANCHOR: int = 155_848  # cestas distintas (COUNT DISTINCT basket_id)
LINE_ANCHOR: int = 1_469_307  # linhas item-de-linha (= SUM(n_items) em fct_basket)
HOUSEHOLD_UNIVERSE: int = 2_469  # domicílios distintos (todos com >= 1 cesta)

# Âncoras factuais de campanha/cupom (Marketing Analytics), ver docs/metrics.md
# §8.0.1. São FATOS dos dados — conferidos por prototipagem real sobre o Parquet
# Silver em 2026-10-14. Estas tabelas Gold NUNCA tocam em sales_value (regra
# anti-fan-out §8.0.2): nenhuma delas soma receita.
CAMPAIGN_COUNT: int = 27  # campanhas (campaign_descriptions), tipos Type A/B/C
CAMPAIGN_EXPOSURE_ANCHOR: int = 6_589  # exposições = linhas da ponte domicílio×campanha
EXPOSED_HOUSEHOLDS_ANCHOR: int = 1_559  # domicílios distintos expostos (63,1% dos 2.469)
REDEMPTION_EVENT_ANCHOR: int = 2_102  # eventos de resgate (coupon_redemptions)
REDEEMER_HOUSEHOLDS_ANCHOR: int = 410  # domicílios distintos que resgataram (26,3% dos expostos)
COUPONS_REDEEMED_ANCHOR: int = 491  # cupons distintos resgatados (de 981)
# Pares (domicílio, campanha) distintos que resgataram = SUM(households_redeemed)
# por campanha = numerador da taxa de resposta por oferta (§8.2.b). 792/6.589 = 12,0%.
REDEEMER_PAIRS_ANCHOR: int = 792

# Data de referência (as-of) FIXA para recência — a máxima data observada.
# NUNCA a data atual do computador (CLAUDE.md regra 8 / metrics.md §0).
AS_OF_DATE: str = "2018-01-01"
# Janela observada das transações (fronteiras de mês para a base de atividade).
# A fato vai até 2018-01-01 04:01:20 (fim da semana 53) => há um mês-fronteira
# parcial 2018-01 (sliver de 77 domicílios que compraram em 01/01/2018).
DATA_WINDOW_START: str = "2017-01-01"
DATA_WINDOW_END: str = "2018-01-01"


@dataclass(frozen=True)
class TableSpec:
    """Especificação de ingestão fiel (1:1) de uma tabela de origem.

    Attributes:
        name: nome lógico da tabela Bronze (vira a pasta de saída).
        source_file: arquivo bruto em ``data/raw/completejourney/``.
        expected_rows: contagem de linhas esperada (asset check). Fonte:
            inspeção documentada em docs/data-dictionary.md.
        id_columns: colunas que são códigos (não números) — forçadas a string.
        partition_by: coluna de particionamento no Parquet (``week`` para as
            tabelas pesadas), ou ``None`` para arquivo único.
    """

    name: str
    source_file: str
    expected_rows: int
    id_columns: tuple[str, ...] = field(default_factory=tuple)
    partition_by: str | None = None

    @property
    def source_path(self) -> Path:
        return RAW_DIR / self.source_file

    @property
    def output_dir(self) -> Path:
        return BRONZE_DIR / self.name


# Ordem/contagens conferidas contra docs/data-dictionary.md e SHA256SUMS.txt.
TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        name="transactions",
        source_file="transactions.rds",
        expected_rows=1_469_307,
        id_columns=("household_id", "store_id", "basket_id", "product_id"),
        partition_by="week",
    ),
    TableSpec(
        name="promotions",
        source_file="promotions.rds",
        expected_rows=20_940_529,
        id_columns=("product_id", "store_id"),
        partition_by="week",
    ),
    TableSpec(
        name="products",
        source_file="products.rda",
        expected_rows=92_331,
        id_columns=("product_id", "manufacturer_id"),
    ),
    TableSpec(
        name="coupons",
        source_file="coupons.rda",
        expected_rows=116_204,
        id_columns=("coupon_upc", "product_id", "campaign_id"),
    ),
    TableSpec(
        name="coupon_redemptions",
        source_file="coupon_redemptions.rda",
        expected_rows=2_102,
        id_columns=("household_id", "coupon_upc", "campaign_id"),
    ),
    TableSpec(
        name="campaigns",
        source_file="campaigns.rda",
        expected_rows=6_589,
        id_columns=("campaign_id", "household_id"),
    ),
    TableSpec(
        name="campaign_descriptions",
        source_file="campaign_descriptions.rda",
        expected_rows=27,
        id_columns=("campaign_id",),
    ),
    TableSpec(
        name="demographics",
        source_file="demographics.rda",
        expected_rows=801,
        id_columns=("household_id",),
    ),
)

TABLE_SPECS_BY_NAME: dict[str, TableSpec] = {spec.name: spec for spec in TABLE_SPECS}

# Nomes das colunas técnicas de auditoria adicionadas a toda tabela Bronze.
AUDIT_COLUMNS: tuple[str, ...] = (
    "_source_file",
    "_ingested_at",
    "_row_count",
    "_source_sha256",
)


def load_expected_hashes(sha_file: Path = SHA256SUMS_FILE) -> dict[str, str]:
    """Lê ``SHA256SUMS.txt`` e devolve ``{nome_arquivo: sha256}``.

    Formato de cada linha: ``<hash> *<arquivo>`` (o ``*`` marca modo binário
    na convenção do coreutils ``sha256sum``).
    """
    hashes: dict[str, str] = {}
    for raw_line in sha_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        digest, _, filename = line.partition(" ")
        filename = filename.lstrip("*").strip()
        if digest and filename:
            hashes[filename] = digest.lower()
    return hashes
