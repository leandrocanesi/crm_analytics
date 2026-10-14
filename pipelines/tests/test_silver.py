"""Testes rápidos da camada Silver.

Rodam o SQL de transformação Silver diretamente sobre o Parquet Bronze (via
DuckDB em memória), sem depender de uma materialização Dagster prévia. Usam
apenas tabelas pequenas/médias para rodar em segundos — transactions e
promotions são exercitadas na materialização real.
"""

from __future__ import annotations

import duckdb
import pytest

from crm_pipelines.silver import _resolve_transform_sql
from crm_pipelines.silver_config import SILVER_SPECS_BY_NAME


def _run(table: str) -> duckdb.DuckDBPyRelation:
    """Executa a transformação Silver de uma tabela sobre o Parquet Bronze."""
    spec = SILVER_SPECS_BY_NAME[table]
    con = duckdb.connect()
    return con.sql(_resolve_transform_sql(spec))


def test_coupons_exact_dedupe() -> None:
    """Dedupe exato por (coupon_upc, product_id, campaign_id): 116.204 → 111.332."""
    rel = _run("coupons")
    n = rel.aggregate("COUNT(*) AS n").fetchone()[0]
    distinct = rel.aggregate(
        "COUNT(DISTINCT (coupon_upc, product_id, campaign_id)) AS d"
    ).fetchone()[0]
    assert n == 111_332
    assert n == distinct  # sem duplicatas remanescentes


def test_demographics_nulls_become_unknown() -> None:
    """home_ownership/marital_status nulos viram 'Unknown'; has_demographics=TRUE."""
    con = duckdb.connect()
    sql = _resolve_transform_sql(SILVER_SPECS_BY_NAME["demographics"])
    row = con.execute(
        f"""SELECT
            SUM(CASE WHEN home_ownership IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN marital_status IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN home_ownership = 'Unknown' THEN 1 ELSE 0 END),
            SUM(CASE WHEN marital_status = 'Unknown' THEN 1 ELSE 0 END),
            BOOL_AND(has_demographics)
        FROM ({sql})"""
    ).fetchone()
    assert row[0] == 0 and row[1] == 0  # nenhum nulo após tratamento
    assert row[2] == 233 and row[3] == 137  # nulos reais convertidos
    assert row[4] is True


def test_products_brand_within_domain() -> None:
    """brand só assume valores do domínio observado {National, Private}."""
    con = duckdb.connect()
    sql = _resolve_transform_sql(SILVER_SPECS_BY_NAME["products"])
    bad = con.execute(
        f"SELECT COUNT(*) FROM ({sql}) WHERE brand NOT IN ('National', 'Private')"
    ).fetchone()[0]
    assert bad == 0


def test_monetary_columns_are_decimal() -> None:
    """Colunas monetárias de transactions são tipadas como DECIMAL(12,2)."""
    con = duckdb.connect()
    sql = _resolve_transform_sql(SILVER_SPECS_BY_NAME["transactions"])
    rows = con.execute(f"DESCRIBE SELECT * FROM ({sql})").fetchall()
    types = {r[0]: r[1] for r in rows}
    for col in ("sales_value", "retail_disc", "coupon_disc", "coupon_match_disc"):
        assert types[col] == "DECIMAL(12,2)", f"{col} = {types[col]}"


@pytest.mark.parametrize(
    "table", ["coupons", "demographics", "products", "campaign_descriptions", "campaigns"]
)
def test_transform_sql_resolves_without_placeholder(table: str) -> None:
    """O SQL resolvido não deixa placeholders e executa sem erro."""
    sql = _resolve_transform_sql(SILVER_SPECS_BY_NAME[table])
    assert "{" not in sql and "}" not in sql
    duckdb.connect().execute(f"SELECT * FROM ({sql}) LIMIT 1")


def test_all_bronze_deps_includes_refs() -> None:
    """coupons declara products e campaign_descriptions como dependências de FK."""
    deps = SILVER_SPECS_BY_NAME["coupons"].all_bronze_deps
    assert deps[0] == "coupons"  # origem primeiro
    assert set(deps) == {"coupons", "products", "campaign_descriptions"}
