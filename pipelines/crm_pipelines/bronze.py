"""Camada Bronze — ingestão FIEL (1:1) dos arquivos .rds/.rda em Parquet.

Um software-defined asset por tabela de origem. Cada asset:
  1. calcula o SHA-256 do arquivo bruto e confere com ``SHA256SUMS.txt``;
  2. lê o DataFrame com ``pyreadr`` (sem limpeza semântica);
  3. força colunas de ID para ``string`` (são códigos, não números);
  4. anexa colunas técnicas de auditoria (``_source_file``, ``_ingested_at``,
     ``_row_count``, ``_source_sha256``);
  5. grava Parquet em ``data/processed/bronze/<tabela>/`` de forma idempotente
     (a pasta é recriada do zero a cada execução → sem acúmulo de arquivos);
     tabelas pesadas (transactions, promotions) são particionadas por ``week``;
  6. emite metadados de materialização observáveis e roda os asset checks.

NÃO há dedupe, tratamento de órfãos, tipagem fina nem normalização de datas —
isso é responsabilidade da Silver. A Bronze é um espelho verificável da origem.

Reprodutibilidade: a coluna ``_ingested_at`` é um carimbo de auditoria (hora de
execução) e, por isso, varia entre execuções. A garantia de reprodutibilidade é
sobre o *conteúdo de negócio*: o metadado ``content_sha256`` (hash das colunas
de origem, sem as de auditoria) é idêntico a cada reexecução com o mesmo input
— exatamente o "mesmo hash de conteúdo" de docs/data-model.md §5.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetCheckSpec,
    AssetsDefinition,
    MaterializeResult,
    MetadataValue,
    asset,
)

from .config import (
    REVENUE_ANCHOR_TOL_USD,
    REVENUE_ANCHOR_USD,
    TableSpec,
    load_expected_hashes,
)
from .readers import coerce_id_columns, read_r_dataframe, sha256_file

# Nomes dos asset checks (reutilizados em specs e resultados).
CHECK_ROW_COUNT = "row_count_matches_expected"
CHECK_SCHEMA = "schema_not_empty"
CHECK_SOURCE_HASH = "source_sha256_matches"
CHECK_REVENUE = "revenue_anchor"


def _content_sha256(frame: pd.DataFrame) -> str:
    """Hash determinístico do conteúdo de negócio (ordem de linhas preservada).

    Combina o schema (nomes de colunas na ordem) com o hash por linha do pandas.
    Dado o mesmo arquivo de origem, o resultado é estável entre execuções — é a
    prova de idempotência/reprodutibilidade da ingestão.
    """
    row_hashes = pd.util.hash_pandas_object(frame, index=False)
    digest = hashlib.sha256()
    digest.update("|".join(map(str, frame.columns)).encode("utf-8"))
    digest.update(row_hashes.to_numpy().tobytes())
    return digest.hexdigest()


def _write_parquet(frame: pd.DataFrame, spec: TableSpec) -> int:
    """Grava a tabela em Parquet de forma idempotente. Devolve bytes gravados.

    A pasta de saída é removida e recriada (semântica CREATE OR REPLACE), logo
    reexecutar não deixa arquivos órfãos de execuções anteriores.
    """
    out_dir = spec.output_dir
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    table = pa.Table.from_pandas(frame, preserve_index=False)

    if spec.partition_by is not None:
        # Particionamento Hive por semana (week=1/…, week=2/…) para leitura
        # eficiente das tabelas pesadas. basename_template fixo → nomes de
        # arquivo estáveis (uma parte por partição).
        pq.write_to_dataset(
            table,
            root_path=str(out_dir),
            partition_cols=[spec.partition_by],
            basename_template="part-{i}.parquet",
            existing_data_behavior="delete_matching",
        )
    else:
        pq.write_table(table, out_dir / f"{spec.name}.parquet")

    return sum(p.stat().st_size for p in out_dir.rglob("*.parquet"))


def _schema_metadata(frame: pd.DataFrame) -> MetadataValue:
    """Amostra de schema (coluna → dtype) como tabela Markdown para a UI."""
    lines = ["| coluna | dtype |", "|---|---|"]
    lines += [f"| `{col}` | {dtype} |" for col, dtype in frame.dtypes.items()]
    return MetadataValue.md("\n".join(lines))


def build_bronze_asset(spec: TableSpec) -> AssetsDefinition:
    """Fabrica o asset Bronze (+ asset checks) de uma tabela de origem."""

    check_specs = [
        AssetCheckSpec(
            name=CHECK_ROW_COUNT,
            asset=spec.name,
            description=f"Contagem de linhas == {spec.expected_rows:,} (esperado).",
        ),
        AssetCheckSpec(
            name=CHECK_SCHEMA,
            asset=spec.name,
            description="Schema tem ao menos uma coluna de origem (não-vazio).",
        ),
        AssetCheckSpec(
            name=CHECK_SOURCE_HASH,
            asset=spec.name,
            description="SHA-256 do arquivo bruto confere com SHA256SUMS.txt.",
        ),
    ]
    if spec.name == "transactions":
        check_specs.append(
            AssetCheckSpec(
                name=CHECK_REVENUE,
                asset=spec.name,
                description=(
                    f"SUM(sales_value) ≈ US$ {REVENUE_ANCHOR_USD:,.2f} "
                    "(teste-âncora de receita, data-model §4)."
                ),
            )
        )

    @asset(
        name=spec.name,
        group_name="bronze",
        kinds={"python", "parquet"},
        description=(
            f"Bronze — ingestão fiel 1:1 de `{spec.source_file}` "
            f"({spec.expected_rows:,} linhas esperadas). Sem limpeza semântica."
        ),
        check_specs=check_specs,
    )
    def _bronze_asset(context):
        # --- 1. Verificação de integridade do arquivo bruto -----------------
        source_sha = sha256_file(spec.source_path)
        expected_sha = load_expected_hashes().get(spec.source_file)
        hash_ok = expected_sha is not None and source_sha == expected_sha

        # --- 2. Leitura fiel + normalização mínima de IDs -------------------
        frame = read_r_dataframe(spec.source_path)
        frame = coerce_id_columns(frame, spec.id_columns)
        source_columns = list(frame.columns)
        row_count = int(len(frame))
        content_sha = _content_sha256(frame)

        context.log.info(
            "%s: %s linhas, %s colunas, hash_ok=%s",
            spec.name,
            f"{row_count:,}",
            len(source_columns),
            hash_ok,
        )

        # --- 3. Teste-âncora de receita (só transactions) ------------------
        revenue_sum: float | None = None
        if spec.name == "transactions":
            revenue_sum = round(float(frame["sales_value"].sum()), 2)

        # --- 4. Colunas técnicas de auditoria ------------------------------
        frame["_source_file"] = spec.source_file
        frame["_ingested_at"] = datetime.now(UTC)
        frame["_row_count"] = row_count
        frame["_source_sha256"] = source_sha

        # --- 5. Gravação idempotente em Parquet ----------------------------
        size_bytes = _write_parquet(frame, spec)

        # --- 6. Metadados de materialização observáveis --------------------
        metadata: dict[str, object] = {
            "dagster/row_count": MetadataValue.int(row_count),
            "expected_rows": MetadataValue.int(spec.expected_rows),
            "num_source_columns": MetadataValue.int(len(source_columns)),
            "source_file": MetadataValue.text(spec.source_file),
            "source_sha256": MetadataValue.text(source_sha),
            "source_hash_ok": MetadataValue.bool(hash_ok),
            "content_sha256": MetadataValue.text(content_sha),
            "output_path": MetadataValue.path(str(spec.output_dir)),
            "output_size_bytes": MetadataValue.int(size_bytes),
            "partitioned_by": MetadataValue.text(spec.partition_by or "—"),
            "schema": _schema_metadata(frame[source_columns]),
        }
        if revenue_sum is not None:
            metadata["revenue_sum_usd"] = MetadataValue.float(revenue_sum)

        yield MaterializeResult(metadata=metadata)

        # --- 7. Asset checks ------------------------------------------------
        yield AssetCheckResult(
            check_name=CHECK_ROW_COUNT,
            passed=row_count == spec.expected_rows,
            severity=AssetCheckSeverity.ERROR,
            metadata={
                "observed": MetadataValue.int(row_count),
                "expected": MetadataValue.int(spec.expected_rows),
            },
        )
        yield AssetCheckResult(
            check_name=CHECK_SCHEMA,
            passed=len(source_columns) > 0,
            severity=AssetCheckSeverity.ERROR,
            metadata={"num_source_columns": MetadataValue.int(len(source_columns))},
        )
        yield AssetCheckResult(
            check_name=CHECK_SOURCE_HASH,
            passed=hash_ok,
            severity=AssetCheckSeverity.ERROR,
            metadata={
                "observed_sha256": MetadataValue.text(source_sha),
                "expected_sha256": MetadataValue.text(expected_sha or "(ausente)"),
            },
        )
        if spec.name == "transactions" and revenue_sum is not None:
            delta = abs(revenue_sum - REVENUE_ANCHOR_USD)
            yield AssetCheckResult(
                check_name=CHECK_REVENUE,
                passed=delta <= REVENUE_ANCHOR_TOL_USD,
                severity=AssetCheckSeverity.ERROR,
                metadata={
                    "observed_usd": MetadataValue.float(revenue_sum),
                    "anchor_usd": MetadataValue.float(REVENUE_ANCHOR_USD),
                    "abs_delta_usd": MetadataValue.float(round(delta, 4)),
                },
            )

    return _bronze_asset
