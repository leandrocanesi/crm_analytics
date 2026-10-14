"""Testes da publicação de snapshot DuckDB.

Cobrem o contrato crítico (CLAUDE.md regra 6 / docs/snapshots.md):
  - a validação é um GATE: se um check falha, nada é publicado e o snapshot
    atual fica intacto;
  - após publicar, ``current.json`` aponta para um arquivo existente;
  - o snapshot publicado abre em ``read_only=True`` e as 4 tabelas Gold
    reconciliam com a âncora de receita (US$ 4.596.039,58).

Os testes escrevem em diretórios temporários (``tmp_path``) — nunca tocam o
``data/snapshots/`` real — mas leem o Parquet Gold real de ``data/processed/gold``
(são pulados se o Gold ainda não foi materializado).
"""

from __future__ import annotations

import dataclasses

import duckdb
import pytest

from crm_pipelines.config import (
    BASKET_ANCHOR,
    GOLD_DIR,
    HOUSEHOLD_UNIVERSE,
    REVENUE_ANCHOR_USD,
)
from crm_pipelines.snapshot import (
    SnapshotValidationError,
    build_staging,
    materialize_snapshot,
    publish_snapshot,
    read_current,
    validate_staging,
)
from crm_pipelines.snapshot_config import (
    GOLD_SNAPSHOT_TABLES,
    VALIDATION_CHECKS,
    SnapshotCheck,
)

# O Gold precisa estar materializado em disco (arquivo único por tabela).
_gold_ready = all(
    (GOLD_DIR / t / f"{t}.parquet").exists() for t in GOLD_SNAPSHOT_TABLES
)
_needs_gold = pytest.mark.skipif(
    not _gold_ready,
    reason="Gold ainda não materializado (rode os assets gold.* primeiro).",
)


@_needs_gold
def test_validation_blocks_publication_when_a_check_fails(tmp_path) -> None:
    """Gate: um check impossível aborta a publicação e não cria nenhum artefato."""
    impossible = SnapshotCheck(
        name="impossible_revenue",
        description="Check que nunca passa (prova o gate).",
        sql="SELECT SUM(basket_revenue) FROM fct_basket",
        expected=-1.0,  # receita jamais é negativa
        tol=0.0,
    )
    checks = VALIDATION_CHECKS + (impossible,)

    with pytest.raises(SnapshotValidationError):
        materialize_snapshot(
            snapshots_dir=tmp_path, gold_dir=GOLD_DIR, checks=checks
        )

    # Nada publicado: sem ponteiro e sem snapshot versionado.
    assert read_current(tmp_path) is None
    assert not list(tmp_path.glob("snapshot_*.duckdb"))
    # O staging também não fica para trás.
    assert not (tmp_path / ".staging" / "snapshot.duckdb.tmp").exists()


@_needs_gold
def test_failed_validation_leaves_previous_snapshot_intact(tmp_path) -> None:
    """Um segundo build que falha NÃO altera o current.json de uma publicação boa."""
    first = materialize_snapshot(snapshots_dir=tmp_path, gold_dir=GOLD_DIR)
    before = read_current(tmp_path)
    assert before is not None

    impossible = SnapshotCheck(
        name="impossible_count",
        description="Check que nunca passa.",
        sql="SELECT COUNT(*) FROM fct_basket",
        expected=1.0,
        tol=0.0,
    )
    with pytest.raises(SnapshotValidationError):
        materialize_snapshot(
            snapshots_dir=tmp_path,
            gold_dir=GOLD_DIR,
            checks=VALIDATION_CHECKS + (impossible,),
        )

    after = read_current(tmp_path)
    assert after == before  # ponteiro intacto
    assert after["active"] == first.active_file
    assert (tmp_path / after["active"]).exists()


@_needs_gold
def test_current_points_to_existing_file_and_opens_read_only(tmp_path) -> None:
    """Pós-publicação: current.json aponta p/ arquivo que abre em read_only."""
    result = materialize_snapshot(snapshots_dir=tmp_path, gold_dir=GOLD_DIR)

    current = read_current(tmp_path)
    assert current is not None
    active = tmp_path / current["active"]
    assert active.exists()
    assert current["active"] == result.active_file
    assert current["checks"] == "passed"

    # Contrato da API: abrir em read_only=True e NUNCA escrever.
    con = duckdb.connect(str(active), read_only=True)
    try:
        tables = {
            r[0] for r in con.execute("SHOW TABLES").fetchall()
        }
        for t in GOLD_SNAPSHOT_TABLES:
            assert t in tables
        assert "_snapshot_meta" in tables
    finally:
        con.close()


@_needs_gold
def test_published_snapshot_reconciles_anchors(tmp_path) -> None:
    """As 4 tabelas reconciliam receita/contagens dentro do snapshot publicado."""
    result = materialize_snapshot(snapshots_dir=tmp_path, gold_dir=GOLD_DIR)
    active = tmp_path / read_current(tmp_path)["active"]

    con = duckdb.connect(str(active), read_only=True)
    try:
        rev_basket = con.execute("SELECT SUM(basket_revenue) FROM fct_basket").fetchone()[0]
        rev_weekly = con.execute("SELECT SUM(revenue) FROM agg_weekly_revenue").fetchone()[0]
        rev_rfm = con.execute("SELECT SUM(monetary_value) FROM agg_household_rfm").fetchone()[0]
        n_baskets = con.execute("SELECT COUNT(*) FROM fct_basket").fetchone()[0]
        n_households = con.execute("SELECT COUNT(*) FROM agg_household_rfm").fetchone()[0]
    finally:
        con.close()

    assert float(rev_basket) == pytest.approx(REVENUE_ANCHOR_USD, abs=0.01)
    assert float(rev_weekly) == pytest.approx(REVENUE_ANCHOR_USD, abs=0.01)
    assert float(rev_rfm) == pytest.approx(REVENUE_ANCHOR_USD, abs=0.01)
    assert n_baskets == BASKET_ANCHOR
    assert n_households == HOUSEHOLD_UNIVERSE
    # O metadado publicado bate com a âncora.
    assert result.revenue_total == pytest.approx(REVENUE_ANCHOR_USD, abs=0.01)


@_needs_gold
def test_content_hash_is_deterministic_version_is_not(tmp_path) -> None:
    """Mesmo Gold => mesmo content_hash; a versão varia pelo carimbo de tempo (by design)."""
    b1 = build_staging(snapshots_dir=tmp_path / "a", gold_dir=GOLD_DIR)
    b2 = build_staging(snapshots_dir=tmp_path / "b", gold_dir=GOLD_DIR)
    assert b1.content_hash == b2.content_hash
    # A versão contém o hash determinístico como sufixo.
    assert b1.version.endswith(b1.content_hash)


@_needs_gold
def test_retention_keeps_last_n_snapshots(tmp_path) -> None:
    """Retenção mantém no máximo N snapshots; o ativo nunca é removido."""
    keep = 2
    last = None
    for i in range(4):
        build = build_staging(snapshots_dir=tmp_path, gold_dir=GOLD_DIR)
        # Versões colidem se construídas no mesmo segundo; força nomes distintos.
        build = dataclasses.replace(build, version=f"{build.version}_{i}")
        last = publish_snapshot(
            build, validate_staging(build.path), snapshots_dir=tmp_path, retention=keep
        )
    snaps = list(tmp_path.glob("snapshot_*.duckdb"))
    assert len(snaps) == keep
    # O ativo sobrevive e o ponteiro aponta para ele.
    assert (tmp_path / last.active_file).exists()
    assert read_current(tmp_path)["active"] == last.active_file


def test_snapshot_check_evaluate_comparators() -> None:
    """A lógica de comparador (eq/ge) do SnapshotCheck está correta (unidade pura)."""
    eq = SnapshotCheck(name="x", description="", sql="", expected=100.0, tol=0.01)
    assert eq.evaluate(100.0)
    assert eq.evaluate(100.005)
    assert not eq.evaluate(100.5)
    ge = SnapshotCheck(
        name="y", description="", sql="", expected=1.0, comparator="ge"
    )
    assert ge.evaluate(1.0)
    assert ge.evaluate(500.0)
    assert not ge.evaluate(0.0)
