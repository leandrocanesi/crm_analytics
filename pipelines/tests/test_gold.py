"""Testes rápidos da camada Gold.

Rodam o SQL de transformação Gold diretamente sobre o Parquet de montante
(Silver para ``fct_basket``; o próprio ``fct_basket`` materializado para os
agregados) via DuckDB em memória. São rápidos: as tabelas Gold são pequenas
(<= 155.848 linhas). Validam as reconciliações com a âncora de receita, a lógica
de segmento RFM e a resolução dos placeholders de dependência.
"""

from __future__ import annotations

import duckdb
import pytest

from crm_pipelines.config import (
    BASKET_ANCHOR,
    GOLD_DIR,
    HOUSEHOLD_UNIVERSE,
    LINE_ANCHOR,
    REVENUE_ANCHOR_USD,
)
from crm_pipelines.gold import _resolve_transform_sql
from crm_pipelines.gold_config import GOLD_SPECS_BY_NAME

# Os agregados dependem de gold.fct_basket já materializado em disco.
_FCT_BASKET_PARQUET = (GOLD_DIR / "fct_basket" / "fct_basket.parquet").as_posix()
_needs_fct_basket = pytest.mark.skipif(
    not (GOLD_DIR / "fct_basket" / "fct_basket.parquet").exists(),
    reason="gold.fct_basket ainda não materializado (rode o asset Gold primeiro).",
)


def _fct_basket_sql() -> str:
    """SQL de fct_basket resolvido sobre o Parquet Silver (não exige Gold em disco)."""
    return _resolve_transform_sql(GOLD_SPECS_BY_NAME["fct_basket"])


def test_placeholders_resolve_without_braces() -> None:
    """Todo SQL Gold resolve seus placeholders de dependência (nada de {..} solto)."""
    for spec in GOLD_SPECS_BY_NAME.values():
        sql = _resolve_transform_sql(spec)
        assert "{" not in sql and "}" not in sql, spec.name


def test_fct_basket_reconciles_anchors() -> None:
    """fct_basket reconcilia receita, nº de cestas e nº de linhas (as 3 âncoras)."""
    con = duckdb.connect()
    row = con.execute(
        f"""SELECT
            COUNT(*)                  AS n_rows,
            COUNT(DISTINCT basket_id) AS n_baskets,
            SUM(basket_revenue)       AS revenue,
            SUM(n_items)              AS items
        FROM ({_fct_basket_sql()})"""
    ).fetchone()
    assert row[0] == BASKET_ANCHOR
    assert row[1] == BASKET_ANCHOR
    assert float(row[2]) == pytest.approx(REVENUE_ANCHOR_USD, abs=0.01)
    assert row[3] == LINE_ANCHOR


def test_fct_basket_grain_is_one_row_per_basket() -> None:
    """Grão de fct_basket: exatamente 1 linha por basket_id (sem duplicação)."""
    con = duckdb.connect()
    dup = con.execute(
        f"SELECT COUNT(*) - COUNT(DISTINCT basket_id) FROM ({_fct_basket_sql()})"
    ).fetchone()[0]
    assert dup == 0


def _rfm_on_fct_basket_subset(con: duckdb.DuckDBPyConnection) -> None:
    """Materializa fct_basket em memória para exercitar os agregados que dele dependem."""
    con.execute(f"CREATE TABLE fct_basket AS {_fct_basket_sql()}")


def test_rfm_segment_logic_small_synthetic() -> None:
    """Precedência dos segmentos (§5.2): a 1ª regra satisfeita vence; resto = 'Outros'.

    Usa o CASE exato do SQL de produção sobre linhas sintéticas de scores R/F/M,
    isolando a lógica de rótulo (sem depender dos quintis reais).
    """
    con = duckdb.connect()
    # (r, f, m, segmento_esperado)
    cases = [
        (5, 5, 5, "Campeões"),               # 1ª regra
        (5, 4, 4, "Campeões"),               # precedência: não cai em Leais
        (1, 4, 3, "Leais"),                  # F>=4 e M>=3, R qualquer
        (4, 3, 1, "Potenciais"),             # R>=4 e F em 2..3
        (5, 2, 1, "Potenciais"),             # precedência: F=2 cai em Potenciais, NÃO em Novos
        (5, 1, 1, "Novos"),                  # R=5 e F=1 (<=2 e fora de 2..3) -> Novos
        (2, 4, 4, "Leais"),                  # F>=4 e M>=3 vence 'Em risco'
        (1, 3, 3, "Em risco"),               # R<=2, F>=3, M>=3
        (1, 1, 1, "Hibernando / Perdidos"),  # R<=2 e F<=2
        (3, 3, 1, "Outros"),                 # nenhuma regra
    ]
    con.execute("CREATE TABLE s (r INT, f INT, m INT, expected VARCHAR)")
    con.executemany("INSERT INTO s VALUES (?,?,?,?)", cases)
    rows = con.execute(
        """
        SELECT expected,
            CASE
                WHEN r >= 4 AND f >= 4 AND m >= 4 THEN 'Campeões'
                WHEN f >= 4 AND m >= 3            THEN 'Leais'
                WHEN r >= 4 AND f BETWEEN 2 AND 3 THEN 'Potenciais'
                WHEN r = 5 AND f <= 2            THEN 'Novos'
                WHEN r <= 2 AND f >= 3 AND m >= 3 THEN 'Em risco'
                WHEN r <= 2 AND f <= 2           THEN 'Hibernando / Perdidos'
                ELSE 'Outros'
            END AS got
        FROM s
        """
    ).fetchall()
    for expected, got in rows:
        assert got == expected, f"esperado {expected}, obtido {got}"


@_needs_fct_basket
def test_rfm_reconciles_and_universe() -> None:
    """agg_household_rfm: 2.469 linhas, M reconcilia, F reconcilia, recência em [0,365]."""
    con = duckdb.connect()
    sql = _resolve_transform_sql(GOLD_SPECS_BY_NAME["agg_household_rfm"])
    row = con.execute(
        f"""SELECT COUNT(*), SUM(monetary_value), SUM(frequency_baskets),
                   MIN(recency_days), MAX(recency_days)
            FROM ({sql})"""
    ).fetchone()
    assert row[0] == HOUSEHOLD_UNIVERSE
    assert float(row[1]) == pytest.approx(REVENUE_ANCHOR_USD, abs=0.01)
    assert row[2] == BASKET_ANCHOR
    assert row[3] >= 0 and row[4] <= 365


@_needs_fct_basket
def test_rfm_is_idempotent() -> None:
    """Idempotência: reexecutar o RFM dá o mesmo rótulo por domicílio (desempate estável)."""
    con = duckdb.connect()
    sql = _resolve_transform_sql(GOLD_SPECS_BY_NAME["agg_household_rfm"])
    diff = con.execute(
        f"""
        WITH a AS ({sql}), b AS ({sql})
        SELECT COUNT(*) FROM a JOIN b USING (household_id)
        WHERE a.r_score <> b.r_score OR a.f_score <> b.f_score
           OR a.m_score <> b.m_score OR a.rfm_segment <> b.rfm_segment
        """
    ).fetchone()[0]
    assert diff == 0


@_needs_fct_basket
def test_weekly_revenue_reconciles() -> None:
    """agg_weekly_revenue: 53 semanas, receita reconcilia, ativos <= universo."""
    con = duckdb.connect()
    sql = _resolve_transform_sql(GOLD_SPECS_BY_NAME["agg_weekly_revenue"])
    row = con.execute(
        f"SELECT COUNT(*), SUM(revenue), MAX(n_active_households) FROM ({sql})"
    ).fetchone()
    assert row[0] == 53
    assert float(row[1]) == pytest.approx(REVENUE_ANCHOR_USD, abs=0.01)
    assert row[2] <= HOUSEHOLD_UNIVERSE


@_needs_fct_basket
def test_activity_month_grain_and_revenue() -> None:
    """agg_household_activity_month: grão domicílio×mês único e receita reconcilia."""
    con = duckdb.connect()
    sql = _resolve_transform_sql(GOLD_SPECS_BY_NAME["agg_household_activity_month"])
    row = con.execute(
        f"""SELECT COUNT(*), COUNT(DISTINCT (household_id, activity_month)),
                   SUM(monthly_revenue)
            FROM ({sql})"""
    ).fetchone()
    assert row[0] == row[1]  # grão único
    assert float(row[2]) == pytest.approx(REVENUE_ANCHOR_USD, abs=0.01)
