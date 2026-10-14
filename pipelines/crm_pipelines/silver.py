"""Camada Silver — tipagem, limpeza, padronização e integridade.

Um software-defined asset por tabela, cada um **dependendo explicitamente** do
asset Bronze correspondente (bronze → silver). As transformações são escritas em
SQL/DuckDB sobre o Parquet Bronze e gravam Parquet em
``data/processed/silver/<tabela>/`` de forma idempotente (a pasta é recriada do
zero a cada execução). O Dagster é o único escritor (CLAUDE.md regra 6); nenhum
snapshot DuckDB é publicado nesta fase.

Princípios (ver docs/data-model.md §5 e decisões aprovadas):
  - **Preserva todas as linhas** — marca, não remove — exceto o dedupe exato de
    ``coupons``.
  - Monetários → ``DECIMAL(12,2)`` (preserva o total de receita US$ 4.596.039,58
    exatamente); IDs → string; datas/timestamps tipados; categóricos validados
    contra domínios observados.
  - Colunas derivadas são rotuladas (``is_*``, ``has_demographics``).
  - FKs **registram** órfãos como metadado (severidade WARN) em vez de falhar —
    órfãos conhecidos (17 produtos de transactions) não quebram o pipeline.

Os asset checks validam o **Parquet Silver já persistido** (não o DataFrame em
memória), de modo que o que foi gravado é exatamente o que é verificado.
"""

from __future__ import annotations

import shutil

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

from .config import (
    BRONZE_DIR,
    REVENUE_ANCHOR_TOL_USD,
    REVENUE_ANCHOR_USD,
    SILVER_DIR,
    TABLE_SPECS_BY_NAME,
)
from .silver_config import SilverSpec

# Limite superior defensivo p/ sanidade de valor monetário por linha (itens
# atípicos vão até US$ 840; qualquer linha acima deste teto é "absurda").
_MONETARY_SANITY_MAX_USD = 100_000.0

# Nomes de asset checks (reutilizados em specs e resultados).
CHECK_ROW_COUNT = "row_count_matches_expected"
CHECK_KEY_NOT_NULL = "key_columns_not_null"
CHECK_PK_UNIQUE = "primary_key_unique"
CHECK_DOMAINS = "categorical_domains_valid"
CHECK_REVENUE = "revenue_preserved"
CHECK_MONETARY = "monetary_values_valid"


# ---------------------------------------------------------------------------
# Expressões de leitura Parquet (Bronze de entrada; Silver para readback/checks).
# ---------------------------------------------------------------------------


def _bronze_src(name: str) -> str:
    """read_parquet do Bronze; hive_partitioning para transactions/promotions."""
    partitioned = TABLE_SPECS_BY_NAME[name].partition_by is not None
    base = (BRONZE_DIR / name).as_posix()
    if partitioned:
        return f"read_parquet('{base}/**/*.parquet', hive_partitioning=true)"
    return f"read_parquet('{base}/*.parquet')"


def _silver_src(spec: SilverSpec) -> str:
    """read_parquet do Silver já gravado (para readback dos checks)."""
    base = (SILVER_DIR / spec.name).as_posix()
    if spec.partition_by is not None:
        return f"read_parquet('{base}/**/*.parquet', hive_partitioning=true)"
    return f"read_parquet('{base}/{spec.name}.parquet')"


def _resolve_transform_sql(spec: SilverSpec) -> str:
    """Resolve os placeholders ``{tabela}`` do SQL para expressões read_parquet."""
    sources = {name: _bronze_src(name) for name in spec.all_bronze_deps}
    return spec.transform_sql.format(**sources)


def _write_silver(con: duckdb.DuckDBPyConnection, spec: SilverSpec, sql: str) -> int:
    """Grava o resultado da transformação em Parquet (idempotente). Devolve bytes.

    A pasta de saída é removida e recriada (semântica CREATE OR REPLACE). Tabelas
    pesadas (transactions, promotions) são reparticionadas por ``week`` via COPY
    nativo do DuckDB — sem materializar 20,9M linhas em memória.
    """
    out_dir = SILVER_DIR / spec.name
    if out_dir.exists():
        shutil.rmtree(out_dir)

    if spec.partition_by is not None:
        # DuckDB cria a árvore week=.../ e mantém a coluna só no caminho (hive),
        # espelhando o layout da Bronze.
        con.execute(
            f"COPY ({sql}) TO '{out_dir.as_posix()}' "
            f"(FORMAT PARQUET, PARTITION_BY ({spec.partition_by}), "
            f"FILENAME_PATTERN 'part-{{i}}', OVERWRITE_OR_IGNORE TRUE)"
        )
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = (out_dir / f"{spec.name}.parquet").as_posix()
        con.execute(f"COPY ({sql}) TO '{target}' (FORMAT PARQUET)")

    return sum(p.stat().st_size for p in out_dir.rglob("*.parquet"))


def _schema_metadata(con: duckdb.DuckDBPyConnection, src: str) -> MetadataValue:
    """Amostra de schema (coluna → tipo) do Parquet Silver como Markdown."""
    rows = con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()
    lines = ["| coluna | tipo |", "|---|---|"]
    lines += [f"| `{r[0]}` | {r[1]} |" for r in rows]
    return MetadataValue.md("\n".join(lines))


# ---------------------------------------------------------------------------
# Fábrica de assets Silver.
# ---------------------------------------------------------------------------


def _build_check_specs(spec: SilverSpec) -> list[AssetCheckSpec]:
    asset_key = AssetKey(["silver", spec.name])
    specs = [
        AssetCheckSpec(
            name=CHECK_ROW_COUNT,
            asset=asset_key,
            description=f"Contagem de linhas == {spec.expected_rows:,} (esperado).",
        ),
        AssetCheckSpec(
            name=CHECK_KEY_NOT_NULL,
            asset=asset_key,
            description=f"Sem nulos nas colunas-chave: {', '.join(spec.key_columns)}.",
        ),
    ]
    if spec.pk_columns:
        specs.append(
            AssetCheckSpec(
                name=CHECK_PK_UNIQUE,
                asset=asset_key,
                description=f"PK única: ({', '.join(spec.pk_columns)}).",
            )
        )
    if spec.domains:
        cols = ", ".join(d.column for d in spec.domains)
        specs.append(
            AssetCheckSpec(
                name=CHECK_DOMAINS,
                asset=asset_key,
                description=f"Categóricos dentro do domínio observado: {cols}.",
            )
        )
    if spec.revenue_check:
        specs.append(
            AssetCheckSpec(
                name=CHECK_REVENUE,
                asset=asset_key,
                description=(
                    f"SUM(sales_value) preservado ≈ US$ {REVENUE_ANCHOR_USD:,.2f} "
                    "(tipagem DECIMAL não altera o total; data-model §3)."
                ),
            )
        )
    if spec.monetary_columns:
        specs.append(
            AssetCheckSpec(
                name=CHECK_MONETARY,
                asset=asset_key,
                description="Monetários sem negativos e dentro de faixa sã.",
            )
        )
    for fk in spec.fks:
        specs.append(
            AssetCheckSpec(
                name=fk.name,
                asset=asset_key,
                description=(
                    f"FK {spec.name}.{fk.column} → {fk.ref_bronze}.{fk.ref_column} "
                    "(registra órfãos; WARN não quebra o pipeline)."
                ),
            )
        )
    return specs


def _null_count(con: duckdb.DuckDBPyConnection, src: str, column: str) -> int:
    row = con.execute(
        f"SELECT COUNT(*) FROM {src} WHERE {column} IS NULL"
    ).fetchone()
    return int(row[0])


def _fk_orphans(
    con: duckdb.DuckDBPyConnection, silver_src: str, fk, bronze_ref_src: str
) -> tuple[int, int]:
    """(linhas órfãs, chaves distintas órfãs) de uma FK contra a referência."""
    sql = f"""
        SELECT COUNT(*) AS orphan_rows,
               COUNT(DISTINCT s.{fk.column}) AS orphan_keys
        FROM {silver_src} s
        LEFT JOIN (SELECT DISTINCT {fk.ref_column} AS k FROM {bronze_ref_src}) r
               ON s.{fk.column} = r.k
        WHERE s.{fk.column} IS NOT NULL AND r.k IS NULL
    """
    row = con.execute(sql).fetchone()
    return int(row[0]), int(row[1])


def build_silver_asset(spec: SilverSpec) -> AssetsDefinition:
    """Fabrica o asset Silver (+ asset checks) de uma tabela."""

    check_specs = _build_check_specs(spec)

    @asset(
        name=spec.name,
        key_prefix="silver",
        group_name="silver",
        kinds={"duckdb", "parquet"},
        deps=list(spec.all_bronze_deps),
        description=(
            f"Silver — tipagem/limpeza/integridade de `{spec.bronze_source}` "
            f"({spec.expected_rows:,} linhas). Preserva linhas (marca, não remove)."
        ),
        check_specs=check_specs,
    )
    def _silver_asset(context):
        con = duckdb.connect()
        try:
            # --- 1. Transformação + gravação idempotente -------------------
            transform_sql = _resolve_transform_sql(spec)
            size_bytes = _write_silver(con, spec, transform_sql)
            src = _silver_src(spec)

            # --- 2. Medições sobre o Parquet persistido --------------------
            row_count = int(con.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0])
            context.log.info("silver.%s: %s linhas", spec.name, f"{row_count:,}")

            metadata: dict[str, object] = {
                "dagster/row_count": MetadataValue.int(row_count),
                "expected_rows": MetadataValue.int(spec.expected_rows),
                "output_path": MetadataValue.path(str(SILVER_DIR / spec.name)),
                "output_size_bytes": MetadataValue.int(size_bytes),
                "partitioned_by": MetadataValue.text(spec.partition_by or "—"),
                "source_bronze": MetadataValue.text(spec.bronze_source),
                "schema": _schema_metadata(con, src),
            }

            # Métricas específicas por tabela (metadados observáveis) ---------
            if spec.name == "coupons":
                before = int(
                    con.execute(
                        f"SELECT COUNT(*) FROM {_bronze_src('coupons')}"
                    ).fetchone()[0]
                )
                metadata["dedupe_rows_before"] = MetadataValue.int(before)
                metadata["dedupe_rows_after"] = MetadataValue.int(row_count)
                metadata["dedupe_rows_removed"] = MetadataValue.int(before - row_count)

            revenue_sum: float | None = None
            if spec.revenue_check:
                revenue_sum = float(
                    con.execute(f"SELECT SUM(sales_value) FROM {src}").fetchone()[0]
                )
                metadata["revenue_sum_usd"] = MetadataValue.float(round(revenue_sum, 2))
                flags = con.execute(
                    f"""SELECT
                        SUM(is_zero_qty::INT), SUM(is_free_item::INT),
                        SUM(is_weighted::INT), SUM(is_orphan_product::INT)
                        FROM {src}"""
                ).fetchone()
                metadata["flag_is_zero_qty"] = MetadataValue.int(int(flags[0]))
                metadata["flag_is_free_item"] = MetadataValue.int(int(flags[1]))
                metadata["flag_is_weighted"] = MetadataValue.int(int(flags[2]))
                metadata["flag_is_orphan_product"] = MetadataValue.int(int(flags[3]))

            if spec.name == "demographics":
                metadata["coverage_note"] = MetadataValue.text(
                    "801 de 2.469 domicílios (32,4%) têm demografia — viés de "
                    "cobertura para segmentação. Flag de cobertura sobre o "
                    "universo completo é materializada no Gold (dim_household)."
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

            # 3b. Colunas-chave não-nulas (ERROR).
            null_by_col = {c: _null_count(con, src, c) for c in spec.key_columns}
            total_nulls = sum(null_by_col.values())
            yield AssetCheckResult(
                check_name=CHECK_KEY_NOT_NULL,
                passed=total_nulls == 0,
                severity=AssetCheckSeverity.ERROR,
                metadata={
                    "total_key_nulls": MetadataValue.int(total_nulls),
                    "nulls_by_column": MetadataValue.json(null_by_col),
                },
            )

            # 3c. PK única (ERROR), quando há PK natural limpa.
            if spec.pk_columns:
                pk_expr = ", ".join(spec.pk_columns)
                dup = int(
                    con.execute(
                        f"SELECT COUNT(*) - COUNT(DISTINCT ({pk_expr})) FROM {src}"
                    ).fetchone()[0]
                )
                yield AssetCheckResult(
                    check_name=CHECK_PK_UNIQUE,
                    passed=dup == 0,
                    severity=AssetCheckSeverity.ERROR,
                    metadata={"duplicate_rows": MetadataValue.int(dup)},
                )

            # 3d. Domínios de categóricos (ERROR).
            if spec.domains:
                viol: dict[str, int] = {}
                for d in spec.domains:
                    allowed = ", ".join(f"'{v}'" for v in d.allowed)
                    cond = f"{d.column} NOT IN ({allowed})"
                    if d.allow_null:
                        cond = f"{d.column} IS NOT NULL AND {cond}"
                    else:
                        cond = f"({d.column} IS NULL OR {cond})"
                    n = int(
                        con.execute(
                            f"SELECT COUNT(*) FROM {src} WHERE {cond}"
                        ).fetchone()[0]
                    )
                    viol[d.column] = n
                total_viol = sum(viol.values())
                yield AssetCheckResult(
                    check_name=CHECK_DOMAINS,
                    passed=total_viol == 0,
                    severity=AssetCheckSeverity.ERROR,
                    metadata={
                        "total_violations": MetadataValue.int(total_viol),
                        "violations_by_column": MetadataValue.json(viol),
                    },
                )

            # 3e. Preservação de receita (ERROR) — âncora US$ 4.596.039,58.
            if spec.revenue_check and revenue_sum is not None:
                observed = round(revenue_sum, 2)
                delta = abs(observed - REVENUE_ANCHOR_USD)
                yield AssetCheckResult(
                    check_name=CHECK_REVENUE,
                    passed=delta <= REVENUE_ANCHOR_TOL_USD,
                    severity=AssetCheckSeverity.ERROR,
                    metadata={
                        "observed_usd": MetadataValue.float(observed),
                        "anchor_usd": MetadataValue.float(REVENUE_ANCHOR_USD),
                        "abs_delta_usd": MetadataValue.float(round(delta, 4)),
                    },
                )

            # 3f. Monetários válidos (ERROR) — sem negativos, dentro de faixa sã.
            if spec.monetary_columns:
                neg_cond = " OR ".join(f"{c} < 0" for c in spec.monetary_columns)
                negatives = int(
                    con.execute(
                        f"SELECT COUNT(*) FROM {src} WHERE {neg_cond}"
                    ).fetchone()[0]
                )
                max_sales = float(
                    con.execute(f"SELECT MAX(sales_value) FROM {src}").fetchone()[0]
                )
                absurd = int(
                    con.execute(
                        f"SELECT COUNT(*) FROM {src} "
                        f"WHERE sales_value > {_MONETARY_SANITY_MAX_USD}"
                    ).fetchone()[0]
                )
                yield AssetCheckResult(
                    check_name=CHECK_MONETARY,
                    passed=negatives == 0 and absurd == 0,
                    severity=AssetCheckSeverity.ERROR,
                    metadata={
                        "negative_rows": MetadataValue.int(negatives),
                        "absurd_rows": MetadataValue.int(absurd),
                        "max_sales_value_usd": MetadataValue.float(round(max_sales, 2)),
                    },
                )

            # 3g. Integridade referencial (WARN) — registra órfãos, não quebra.
            for fk in spec.fks:
                orphan_rows, orphan_keys = _fk_orphans(
                    con, src, fk, _bronze_src(fk.ref_bronze)
                )
                yield AssetCheckResult(
                    check_name=fk.name,
                    passed=orphan_rows == 0,
                    severity=AssetCheckSeverity.WARN,
                    metadata={
                        "orphan_rows": MetadataValue.int(orphan_rows),
                        "orphan_distinct_keys": MetadataValue.int(orphan_keys),
                        "reference": MetadataValue.text(
                            f"{fk.ref_bronze}.{fk.ref_column}"
                        ),
                    },
                )
        finally:
            con.close()

    return _silver_asset
