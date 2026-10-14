"""Camada Gold — visões analíticas prontas para a API, com grão explícito.

Um software-defined asset por tabela Gold, cada um **dependendo explicitamente**
dos assets de montante (silver → gold e gold → gold, via ``deps``). As
transformações são escritas em SQL/DuckDB sobre o Parquet de montante e gravam
Parquet em ``data/processed/gold/<tabela>/<tabela>.parquet`` de forma idempotente
(a pasta é recriada do zero a cada execução — semântica CREATE OR REPLACE). O
Dagster é o único escritor (CLAUDE.md regra 6); **nenhum snapshot DuckDB é
publicado nesta fase**.

Ordem de implementação (docs/metrics.md §7): fct_basket → agg_weekly_revenue →
agg_household_rfm → agg_household_activity_month → agg_retention_monthly →
agg_cohort_retention. As tabelas de receita reconciliam com a âncora
US$ 4.596.039,58 (fonte única = a fato; nunca um join que faça fan-out —
data-model §4) e com as contagens (155.848 cestas, 2.469 domicílios); as de
retenção derivam da base de atividade mensal e carregam checks próprios (taxa em
[0,1], numerador <= denominador, partição das coortes = universo).

Os asset checks validam o **Parquet Gold já persistido** (não um DataFrame em
memória): o que foi gravado é exatamente o que é verificado.
"""

from __future__ import annotations

import datetime as dt
import shutil
import time

import duckdb
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetCheckSpec,
    AssetKey,
    AssetsDefinition,
    MaterializeResult,
    MetadataValue,
    asset,
)

from .config import GOLD_DIR, SILVER_DIR, TABLE_SPECS_BY_NAME
from .gold_config import GoldSpec

# Nomes dos asset checks genéricos (os específicos vêm dos descritores da spec).
CHECK_ROW_COUNT = "row_count_matches_expected"
CHECK_GRAIN_UNIQUE = "grain_is_unique"


# ---------------------------------------------------------------------------
# Expressões de leitura Parquet (montante Silver/Gold) e gravação Gold.
# ---------------------------------------------------------------------------


def _silver_src(name: str) -> str:
    """read_parquet do Silver; hive_partitioning para transactions/promotions."""
    partitioned = TABLE_SPECS_BY_NAME[name].partition_by is not None
    base = (SILVER_DIR / name).as_posix()
    if partitioned:
        return f"read_parquet('{base}/**/*.parquet', hive_partitioning=true)"
    return f"read_parquet('{base}/{name}.parquet')"


def _gold_src(name: str) -> str:
    """read_parquet de uma tabela Gold já gravada (arquivo único)."""
    base = (GOLD_DIR / name).as_posix()
    return f"read_parquet('{base}/{name}.parquet')"


def _dep_sources(spec: GoldSpec) -> dict[str, str]:
    """Mapa ``{layer}_{table}`` -> expressão read_parquet das dependências da spec."""
    sources: dict[str, str] = {}
    for layer, table in spec.all_deps:
        key = f"{layer}_{table}"
        sources[key] = _silver_src(table) if layer == "silver" else _gold_src(table)
    return sources


def _resolve_transform_sql(spec: GoldSpec) -> str:
    """Resolve placeholders ``{silver_<t>}`` / ``{gold_<t>}`` do SQL da spec."""
    return spec.transform_sql.format(**_dep_sources(spec))


def _resolve_check_sql(spec: GoldSpec, sql: str) -> str:
    """Resolve o SQL de um IntegrityCheck: ``{this}`` (a própria Gold já gravada)
    + os placeholders de dependência ``{silver_<t>}`` / ``{gold_<t>}``."""
    sources = _dep_sources(spec)
    sources["this"] = _gold_src(spec.name)
    return sql.format(**sources)


def _write_gold(con: duckdb.DuckDBPyConnection, spec: GoldSpec, sql: str) -> int:
    """Grava o resultado em Parquet (arquivo único, idempotente). Devolve bytes.

    A pasta de saída é removida e recriada antes da gravação (CREATE OR REPLACE).
    As tabelas Gold são pequenas (<= 155.848 linhas), então arquivo único mantém
    a leitura da API simples; não há particionamento.
    """
    out_dir = GOLD_DIR / spec.name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = (out_dir / f"{spec.name}.parquet").as_posix()
    con.execute(f"COPY ({sql}) TO '{target}' (FORMAT PARQUET)")
    return sum(p.stat().st_size for p in out_dir.rglob("*.parquet"))


def _schema_metadata(con: duckdb.DuckDBPyConnection, src: str) -> MetadataValue:
    """Amostra de schema (coluna → tipo) do Parquet Gold como Markdown."""
    rows = con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()
    lines = ["| coluna | tipo |", "|---|---|"]
    lines += [f"| `{r[0]}` | {r[1]} |" for r in rows]
    return MetadataValue.md("\n".join(lines))


# ---------------------------------------------------------------------------
# Fábrica de assets Gold.
# ---------------------------------------------------------------------------


def _build_check_specs(spec: GoldSpec) -> list[AssetCheckSpec]:
    asset_key = AssetKey(["gold", spec.name])
    specs = [
        AssetCheckSpec(
            name=CHECK_ROW_COUNT,
            asset=asset_key,
            description=f"Contagem de linhas == {spec.expected_rows:,} (grão: {spec.grain}).",
        ),
        AssetCheckSpec(
            name=CHECK_GRAIN_UNIQUE,
            asset=asset_key,
            description=f"Grão único por ({', '.join(spec.grain_columns)}).",
        ),
    ]
    specs += [
        AssetCheckSpec(name=c.name, asset=asset_key, description=c.description)
        for c in spec.reconcile_checks
    ]
    specs += [
        AssetCheckSpec(name=c.name, asset=asset_key, description=c.description)
        for c in spec.violation_checks
    ]
    specs += [
        AssetCheckSpec(name=c.name, asset=asset_key, description=c.description)
        for c in spec.integrity_checks
    ]
    return specs


def _rfm_segment_metadata(con: duckdb.DuckDBPyConnection, src: str) -> MetadataValue:
    """Distribuição de domicílios por segmento RFM (observabilidade de CRM)."""
    rows = con.execute(
        f"SELECT rfm_segment, COUNT(*) AS n FROM {src} GROUP BY 1 ORDER BY n DESC"
    ).fetchall()
    return MetadataValue.json({r[0]: int(r[1]) for r in rows})


def build_gold_asset(spec: GoldSpec) -> AssetsDefinition:
    """Fabrica o asset Gold (+ asset checks) de uma tabela."""

    check_specs = _build_check_specs(spec)
    dep_keys = [AssetKey([layer, table]) for layer, table in spec.all_deps]

    @asset(
        name=spec.name,
        key_prefix="gold",
        group_name="gold",
        kinds={"duckdb", "parquet"},
        deps=dep_keys,
        description=spec.description or f"Gold — {spec.grain}.",
        check_specs=check_specs,
    )
    def _gold_asset(context):
        con = duckdb.connect()
        try:
            # --- 1. Transformação + gravação idempotente -------------------
            started = time.perf_counter()
            transform_sql = _resolve_transform_sql(spec)
            size_bytes = _write_gold(con, spec, transform_sql)
            duration_s = time.perf_counter() - started
            src = _gold_src(spec.name)

            # --- 2. Medições sobre o Parquet persistido --------------------
            row_count = int(con.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0])
            context.log.info("gold.%s: %s linhas", spec.name, f"{row_count:,}")

            metadata: dict[str, object] = {
                "dagster/row_count": MetadataValue.int(row_count),
                "expected_rows": MetadataValue.int(spec.expected_rows),
                "grain": MetadataValue.text(spec.grain),
                "output_path": MetadataValue.path(str(GOLD_DIR / spec.name)),
                "output_size_bytes": MetadataValue.int(size_bytes),
                "duration_seconds": MetadataValue.float(round(duration_s, 3)),
                "updated_at": MetadataValue.text(
                    dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
                ),
                "upstream_deps": MetadataValue.text(
                    ", ".join(f"{layer}.{t}" for layer, t in spec.all_deps)
                ),
                "schema": _schema_metadata(con, src),
            }

            # Métricas específicas por tabela (observabilidade analítica) ------
            if spec.name == "agg_household_rfm":
                metadata["rfm_segment_distribution"] = _rfm_segment_metadata(con, src)
            if spec.name == "agg_household_activity_month":
                n_boundary = int(
                    con.execute(
                        f"SELECT COUNT(*) FROM {src} "
                        "WHERE activity_month = DATE '2018-01-01'"
                    ).fetchone()[0]
                )
                metadata["months_distinct"] = MetadataValue.int(
                    int(con.execute(
                        f"SELECT COUNT(DISTINCT activity_month) FROM {src}"
                    ).fetchone()[0])
                )
                metadata["boundary_2018_01_rows"] = MetadataValue.int(n_boundary)
                metadata["boundary_note"] = MetadataValue.text(
                    "O mês 2018-01 é a fronteira parcial da semana 53 (domicílios "
                    "que compraram em 01/01/2018) — esperado, não um erro."
                )
            if spec.name == "agg_retention_monthly":
                rates = con.execute(
                    f"SELECT activity_month, round(retention_rate, 4), next_month_partial "
                    f"FROM {src} ORDER BY activity_month"
                ).fetchall()
                metadata["retention_rate_by_month"] = MetadataValue.json(
                    {str(r[0]): float(r[1]) for r in rates}
                )
                metadata["partial_note"] = MetadataValue.text(
                    "A linha 2017-12 -> 2018-01 (next_month_partial=TRUE) usa o mês "
                    "parcial como M+1; a taxa está subestimada (fim da janela, não "
                    "churn). M=2018-01 é omitido como origem. Observacional: sem "
                    "causalidade."
                )
            if spec.name == "agg_cohort_retention":
                sizes = con.execute(
                    f"SELECT cohort_month, ANY_VALUE(cohort_size) FROM {src} "
                    "GROUP BY cohort_month ORDER BY cohort_month"
                ).fetchall()
                metadata["cohort_sizes"] = MetadataValue.json(
                    {str(r[0]): int(r[1]) for r in sizes}
                )
                metadata["left_censoring_note"] = MetadataValue.text(
                    "cohort_month = primeira aparição NA JANELA, NÃO aquisição real. "
                    "A coorte de 2017-01 é inchada porque os dados começam ali — não "
                    "são 'novos de janeiro'. Right-censoring: coortes tardias têm "
                    "menos meses para maturar. Observacional: sem causalidade."
                )

            yield MaterializeResult(metadata=metadata)

            # --- 3. Asset checks -------------------------------------------
            # 3a. Contagem de linhas (ERROR).
            yield AssetCheckResult(
                check_name=CHECK_ROW_COUNT,
                passed=row_count == spec.expected_rows,
                severity=AssetCheckSeverity.ERROR,
                metadata={
                    "observed": MetadataValue.int(row_count),
                    "expected": MetadataValue.int(spec.expected_rows),
                },
            )

            # 3b. Grão único (ERROR) — sem perda nem duplicação no grão declarado.
            grain_expr = ", ".join(spec.grain_columns)
            dup = int(
                con.execute(
                    f"SELECT COUNT(*) - COUNT(DISTINCT ({grain_expr})) FROM {src}"
                ).fetchone()[0]
            )
            yield AssetCheckResult(
                check_name=CHECK_GRAIN_UNIQUE,
                passed=dup == 0,
                severity=AssetCheckSeverity.ERROR,
                metadata={
                    "duplicate_rows": MetadataValue.int(dup),
                    "grain": MetadataValue.text(grain_expr),
                },
            )

            # 3c. Reconciliações de valor (ERROR) — âncora de receita / contagens.
            for rc in spec.reconcile_checks:
                observed = float(
                    con.execute(f"SELECT {rc.value_expr} FROM {src}").fetchone()[0]
                )
                delta = abs(observed - rc.expected)
                yield AssetCheckResult(
                    check_name=rc.name,
                    passed=delta <= rc.tol,
                    severity=AssetCheckSeverity.ERROR,
                    metadata={
                        "observed": MetadataValue.float(round(observed, 2)),
                        "expected": MetadataValue.float(round(rc.expected, 2)),
                        "abs_delta": MetadataValue.float(round(delta, 4)),
                        "tolerance": MetadataValue.float(rc.tol),
                    },
                )

            # 3d. Checks de violação (ERROR) — contagem de linhas inválidas == 0.
            for vc in spec.violation_checks:
                bad = int(
                    con.execute(
                        f"SELECT COUNT(*) FROM {src} WHERE {vc.where_expr}"
                    ).fetchone()[0]
                )
                yield AssetCheckResult(
                    check_name=vc.name,
                    passed=bad == 0,
                    severity=AssetCheckSeverity.ERROR,
                    metadata={"violating_rows": MetadataValue.int(bad)},
                )

            # 3e. Checks de integridade cross-table (ERROR) — o SQL devolve o nº de
            #     violações (p.ex. meses cujo denominador não bate com a base).
            for ic in spec.integrity_checks:
                check_sql = _resolve_check_sql(spec, ic.count_sql)
                bad = int(con.execute(check_sql).fetchone()[0])
                yield AssetCheckResult(
                    check_name=ic.name,
                    passed=bad == 0,
                    severity=AssetCheckSeverity.ERROR,
                    metadata={"violations": MetadataValue.int(bad)},
                )
        finally:
            con.close()

    return _gold_asset
