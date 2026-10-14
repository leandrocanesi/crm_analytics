"""Configuração estática da camada Silver.

Cada tabela Silver é descrita por um :class:`SilverSpec` que carrega:
  - a dependência Bronze de origem (``bronze_source``) e eventuais tabelas Bronze
    de referência para FKs (``bronze_refs``);
  - o SQL de transformação (``transform_sql``) — tipagem, limpeza, flags e, no
    caso de ``coupons``, o dedupe exato aprovado;
  - as expectativas de validação: contagem de linhas, colunas-chave (não-nulas),
    PK (unicidade), domínios de categóricos, FKs (registram órfãos) e, só em
    ``transactions``, os testes de receita e de valores monetários.

Princípio (CLAUDE.md regra 5): Silver **preserva todas as linhas** — marca, não
remove — exceto o dedupe exato de ``coupons`` (decisão aprovada). Tudo aqui é
determinístico e idempotente: o mesmo Parquet Bronze produz o mesmo Parquet
Silver.

Os números esperados (contagens, domínios) foram conferidos por inspeção real do
Parquet Bronze em 2026-10-14 — ver docs/data-dictionary.md e docs/data-model.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Descritores de validação reutilizados pelos asset checks.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainSpec:
    """Domínio fechado de uma coluna categórica (validado contra o observado).

    O check falha (ERROR) se surgir qualquer valor fora de ``allowed``. Quando
    ``allow_null`` é ``False``, nulos também contam como violação — útil após o
    tratamento de ``demographics`` (nulos viram ``'Unknown'``).
    """

    column: str
    allowed: tuple[str, ...]
    allow_null: bool = False


@dataclass(frozen=True)
class FKSpec:
    """Integridade referencial de uma FK contra uma tabela Bronze de referência.

    O check **registra** a contagem de órfãos como metadado e usa severidade
    WARN: órfãos conhecidos (ex. 17 produtos de transactions sem cadastro) são
    esperados e **não** devem quebrar o pipeline (decisão aprovada #6). O par
    (coluna → ref) assume o mesmo nome de coluna na referência, salvo
    ``ref_column``.
    """

    name: str
    column: str
    ref_bronze: str
    ref_column: str
    ref_partitioned: bool = False


@dataclass(frozen=True)
class SilverSpec:
    """Especificação de uma tabela Silver (transformação + validações)."""

    name: str
    bronze_source: str
    transform_sql: str
    expected_rows: int
    key_columns: tuple[str, ...]
    # Colunas Bronze de referência (p/ FKs) que entram como dependências do asset
    # e ficam disponíveis como fontes nomeadas no SQL/checks.
    bronze_refs: tuple[str, ...] = field(default_factory=tuple)
    partition_by: str | None = None
    pk_columns: tuple[str, ...] = field(default_factory=tuple)
    domains: tuple[DomainSpec, ...] = field(default_factory=tuple)
    fks: tuple[FKSpec, ...] = field(default_factory=tuple)
    # Específico de transactions:
    revenue_check: bool = False
    monetary_columns: tuple[str, ...] = field(default_factory=tuple)

    @property
    def all_bronze_deps(self) -> tuple[str, ...]:
        """Todas as dependências Bronze (origem + referências), sem duplicatas."""
        seen: dict[str, None] = {self.bronze_source: None}
        for ref in self.bronze_refs:
            seen.setdefault(ref, None)
        return tuple(seen)


# ---------------------------------------------------------------------------
# Domínios observados (inspeção real do Parquet Bronze, 2026-10-14).
# ---------------------------------------------------------------------------

_BRAND = (DomainSpec("brand", ("National", "Private")),)

_CAMPAIGN_TYPE = (DomainSpec("campaign_type", ("Type A", "Type B", "Type C")),)

_PROMO_DOMAINS = (
    DomainSpec("display_location", ("0", "1", "2", "3", "4", "5", "6", "7", "9", "A")),
    DomainSpec("mailer_location", ("0", "A", "C", "D", "F", "H", "J", "L", "P", "X", "Z")),
)

_DEMO_DOMAINS = (
    DomainSpec("age", ("19-24", "25-34", "35-44", "45-54", "55-64", "65+")),
    DomainSpec(
        "income",
        (
            "Under 15K", "15-24K", "25-34K", "35-49K", "50-74K", "75-99K",
            "100-124K", "125-149K", "150-174K", "175-199K", "200-249K", "250K+",
        ),
    ),
    # home_ownership / marital_status: nulos reais → 'Unknown' na transformação,
    # por isso 'Unknown' entra no domínio e allow_null=False (sem nulos após tratar).
    DomainSpec(
        "home_ownership",
        ("Homeowner", "Probable Homeowner", "Probable Renter", "Renter", "Unknown"),
    ),
    DomainSpec("marital_status", ("Married", "Unmarried", "Unknown")),
    DomainSpec("household_size", ("1", "2", "3", "4", "5+")),
    DomainSpec(
        "household_comp",
        ("1 Adult Kids", "1 Adult No Kids", "2 Adults Kids", "2 Adults No Kids"),
    ),
    DomainSpec("kids_count", ("0", "1", "2", "3+")),
)


# ---------------------------------------------------------------------------
# SQL de transformação por tabela. Placeholders ``{origem}`` / ``{ref}`` são
# resolvidos em silver.py para expressões read_parquet sobre o Bronze.
# ---------------------------------------------------------------------------

# transactions: tipagem monetária em DECIMAL(12,2) (preserva o total exato),
# IDs string, timestamp/week tipados, e flags derivadas (rotuladas is_*):
#   is_zero_qty / is_free_item / is_weighted  -> decisão aprovada #3
#   is_orphan_product                         -> decisão aprovada #2 (não remove a venda)
_SQL_TRANSACTIONS = """
SELECT
    CAST(t.household_id AS VARCHAR)  AS household_id,
    CAST(t.store_id     AS VARCHAR)  AS store_id,
    CAST(t.basket_id    AS VARCHAR)  AS basket_id,
    CAST(t.product_id   AS VARCHAR)  AS product_id,
    CAST(t.quantity     AS DOUBLE)   AS quantity,
    CAST(t.sales_value       AS DECIMAL(12,2)) AS sales_value,
    CAST(t.retail_disc       AS DECIMAL(12,2)) AS retail_disc,
    CAST(t.coupon_disc       AS DECIMAL(12,2)) AS coupon_disc,
    CAST(t.coupon_match_disc AS DECIMAL(12,2)) AS coupon_match_disc,
    CAST(t.transaction_timestamp AS TIMESTAMP) AS transaction_timestamp,
    CAST(t.week AS INTEGER) AS week,
    (t.quantity    = 0)     AS is_zero_qty,
    (t.sales_value = 0)     AS is_free_item,
    (t.quantity    > 1000)  AS is_weighted,
    (p.product_id IS NULL)  AS is_orphan_product
FROM {transactions} t
LEFT JOIN (SELECT DISTINCT product_id FROM {products}) p USING (product_id)
"""

# promotions: tipagem + flags de conveniência derivadas das categorias de local.
_SQL_PROMOTIONS = """
SELECT
    CAST(product_id AS VARCHAR)       AS product_id,
    CAST(store_id   AS VARCHAR)       AS store_id,
    CAST(display_location AS VARCHAR) AS display_location,
    CAST(mailer_location  AS VARCHAR) AS mailer_location,
    CAST(week AS INTEGER)             AS week,
    (display_location <> '0') AS is_on_display,
    (mailer_location  <> '0') AS is_in_mailer
FROM {promotions}
"""

# products: tipagem; nulos de metadados finos (product_category/type/package_size)
# são preservados (ausência legítima de cadastro, não erro). PK product_id.
_SQL_PRODUCTS = """
SELECT
    CAST(product_id       AS VARCHAR) AS product_id,
    CAST(manufacturer_id  AS VARCHAR) AS manufacturer_id,
    CAST(department       AS VARCHAR) AS department,
    CAST(brand            AS VARCHAR) AS brand,
    CAST(product_category AS VARCHAR) AS product_category,
    CAST(product_type     AS VARCHAR) AS product_type,
    CAST(package_size     AS VARCHAR) AS package_size
FROM {products}
"""

# coupons: dedupe EXATO por (coupon_upc, product_id, campaign_id) — remove só as
# 4.872 linhas idênticas (decisão aprovada #1). SELECT DISTINCT sobre as 3
# colunas de negócio (as colunas de auditoria Bronze não são propagadas).
_SQL_COUPONS = """
SELECT DISTINCT
    CAST(coupon_upc  AS VARCHAR) AS coupon_upc,
    CAST(product_id  AS VARCHAR) AS product_id,
    CAST(campaign_id AS VARCHAR) AS campaign_id
FROM {coupons}
"""

_SQL_COUPON_REDEMPTIONS = """
SELECT
    CAST(household_id    AS VARCHAR) AS household_id,
    CAST(coupon_upc      AS VARCHAR) AS coupon_upc,
    CAST(campaign_id     AS VARCHAR) AS campaign_id,
    CAST(redemption_date AS DATE)    AS redemption_date
FROM {coupon_redemptions}
"""

_SQL_CAMPAIGNS = """
SELECT
    CAST(campaign_id  AS VARCHAR) AS campaign_id,
    CAST(household_id AS VARCHAR) AS household_id
FROM {campaigns}
"""

_SQL_CAMPAIGN_DESCRIPTIONS = """
SELECT
    CAST(campaign_id   AS VARCHAR) AS campaign_id,
    CAST(campaign_type AS VARCHAR) AS campaign_type,
    CAST(start_date    AS DATE)    AS start_date,
    CAST(end_date      AS DATE)    AS end_date
FROM {campaign_descriptions}
"""

# demographics: nulos reais de home_ownership/marital_status → 'Unknown'
# (decisão aprovada #4). has_demographics=TRUE marca, nesta tabela, os 801
# domicílios com perfil; a cobertura sobre o universo de 2.469 domicílios
# (viés de 32,4%) é materializada no Gold (dim_household), fora deste escopo.
_SQL_DEMOGRAPHICS = """
SELECT
    CAST(household_id AS VARCHAR) AS household_id,
    CAST(age    AS VARCHAR) AS age,
    CAST(income AS VARCHAR) AS income,
    COALESCE(CAST(home_ownership AS VARCHAR), 'Unknown') AS home_ownership,
    COALESCE(CAST(marital_status AS VARCHAR), 'Unknown') AS marital_status,
    CAST(household_size AS VARCHAR) AS household_size,
    CAST(household_comp AS VARCHAR) AS household_comp,
    CAST(kids_count     AS VARCHAR) AS kids_count,
    TRUE AS has_demographics
FROM {demographics}
"""


SILVER_SPECS: tuple[SilverSpec, ...] = (
    SilverSpec(
        name="transactions",
        bronze_source="transactions",
        bronze_refs=("products",),
        transform_sql=_SQL_TRANSACTIONS,
        expected_rows=1_469_307,
        partition_by="week",
        key_columns=("household_id", "store_id", "basket_id", "product_id"),
        pk_columns=("basket_id", "product_id"),
        revenue_check=True,
        monetary_columns=(
            "sales_value",
            "retail_disc",
            "coupon_disc",
            "coupon_match_disc",
        ),
        fks=(
            FKSpec(
                name="fk_product_id_in_products",
                column="product_id",
                ref_bronze="products",
                ref_column="product_id",
            ),
        ),
    ),
    SilverSpec(
        name="promotions",
        bronze_source="promotions",
        transform_sql=_SQL_PROMOTIONS,
        expected_rows=20_940_529,
        partition_by="week",
        key_columns=("product_id", "store_id", "week", "display_location", "mailer_location"),
        domains=_PROMO_DOMAINS,
    ),
    SilverSpec(
        name="products",
        bronze_source="products",
        transform_sql=_SQL_PRODUCTS,
        expected_rows=92_331,
        key_columns=("product_id",),
        pk_columns=("product_id",),
        domains=_BRAND,
    ),
    SilverSpec(
        name="coupons",
        bronze_source="coupons",
        bronze_refs=("products", "campaign_descriptions"),
        transform_sql=_SQL_COUPONS,
        expected_rows=111_332,  # após dedupe exato (116.204 - 4.872)
        key_columns=("coupon_upc", "product_id", "campaign_id"),
        pk_columns=("coupon_upc", "product_id", "campaign_id"),
        fks=(
            FKSpec(
                name="fk_product_id_in_products",
                column="product_id",
                ref_bronze="products",
                ref_column="product_id",
            ),
            FKSpec(
                name="fk_campaign_id_in_campaign_descriptions",
                column="campaign_id",
                ref_bronze="campaign_descriptions",
                ref_column="campaign_id",
            ),
        ),
    ),
    SilverSpec(
        name="coupon_redemptions",
        bronze_source="coupon_redemptions",
        bronze_refs=("coupons", "campaign_descriptions"),
        transform_sql=_SQL_COUPON_REDEMPTIONS,
        expected_rows=2_102,
        key_columns=("household_id", "coupon_upc", "campaign_id", "redemption_date"),
        fks=(
            FKSpec(
                name="fk_coupon_upc_in_coupons",
                column="coupon_upc",
                ref_bronze="coupons",
                ref_column="coupon_upc",
            ),
            FKSpec(
                name="fk_campaign_id_in_campaign_descriptions",
                column="campaign_id",
                ref_bronze="campaign_descriptions",
                ref_column="campaign_id",
            ),
        ),
    ),
    SilverSpec(
        name="campaigns",
        bronze_source="campaigns",
        bronze_refs=("campaign_descriptions",),
        transform_sql=_SQL_CAMPAIGNS,
        expected_rows=6_589,
        key_columns=("campaign_id", "household_id"),
        pk_columns=("campaign_id", "household_id"),
        fks=(
            FKSpec(
                name="fk_campaign_id_in_campaign_descriptions",
                column="campaign_id",
                ref_bronze="campaign_descriptions",
                ref_column="campaign_id",
            ),
        ),
    ),
    SilverSpec(
        name="campaign_descriptions",
        bronze_source="campaign_descriptions",
        transform_sql=_SQL_CAMPAIGN_DESCRIPTIONS,
        expected_rows=27,
        key_columns=("campaign_id",),
        pk_columns=("campaign_id",),
        domains=_CAMPAIGN_TYPE,
    ),
    SilverSpec(
        name="demographics",
        bronze_source="demographics",
        transform_sql=_SQL_DEMOGRAPHICS,
        expected_rows=801,
        key_columns=("household_id",),
        pk_columns=("household_id",),
        domains=_DEMO_DOMAINS,
    ),
)

SILVER_SPECS_BY_NAME: dict[str, SilverSpec] = {s.name: s for s in SILVER_SPECS}
