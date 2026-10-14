"""Publicação do snapshot DuckDB — o artefato read-only consumido pela API.

Fluxo (ver ``docs/snapshots.md``):

    build (staging)  ->  validação (gate)  ->  publicação atômica  ->  ponteiro
    .staging/*.tmp       reconcilia âncoras    os.replace p/ nome      current.json
                         (aborta se falhar)    versionado              (os.replace)

Garantias (CLAUDE.md regra 6):
  - **Único escritor:** só o Dagster escreve. A API abre ``read_only=True``.
  - **Nunca disputar escrita:** o build acontece num arquivo temporário; o arquivo
    que a API lê nunca é escrito no lugar.
  - **Validação antes de publicar:** se qualquer check falha, NÃO promove e o
    snapshot atual fica intacto.
  - **Troca atômica:** ``os.replace`` (atômico no mesmo volume, compatível com
    Windows — sem symlink) tanto do arquivo quanto do ponteiro ``current.json``.
    A API vê ou o ponteiro antigo ou o novo, nunca um estado intermediário.

As funções de build/validação/publicação são puras o suficiente para serem
testadas sem o Dagster (aceitam diretórios explícitos). O asset ``published_snapshot``
é um wrapper fino que usa os caminhos padrão de produção.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

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

from .config import GOLD_DIR
from .snapshot_config import (
    CHECK_CURRENT_POINTS_TO_FILE,
    CHECK_OPENS_READ_ONLY,
    CURRENT_FILENAME,
    GOLD_SNAPSHOT_TABLES,
    META_TABLE,
    RETENTION_COUNT,
    SCHEMA_VERSION,
    SNAPSHOT_PREFIX,
    SNAPSHOT_SUFFIX,
    SNAPSHOTS_DIR,
    STAGING_DIRNAME,
    STAGING_FILENAME,
    VALIDATION_CHECKS,
    SnapshotCheck,
    git_commit_short,
)


class SnapshotValidationError(RuntimeError):
    """Levantada quando a validação do staging falha — publicação abortada."""


# ---------------------------------------------------------------------------
# Resultados tipados (observabilidade + retorno testável).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckOutcome:
    name: str
    description: str
    passed: bool
    observed: float
    expected: float
    comparator: str
    tol: float


@dataclass(frozen=True)
class StagingBuild:
    path: Path
    version: str
    built_at: dt.datetime
    content_hash: str
    revenue_total: float
    basket_count: int
    household_count: int
    git_commit: str
    build_seconds: float


@dataclass(frozen=True)
class PublishResult:
    version: str
    active_file: str
    active_path: Path
    current_json: Path
    published_at: dt.datetime
    revenue_total: float
    basket_count: int
    household_count: int
    size_bytes: int
    outcomes: tuple[CheckOutcome, ...]
    retained: tuple[str, ...]
    removed: tuple[str, ...]


# ---------------------------------------------------------------------------
# Helpers de caminho (derivados do diretório de snapshots passado).
# ---------------------------------------------------------------------------


def _staging_dir(snapshots_dir: Path) -> Path:
    return snapshots_dir / STAGING_DIRNAME


def _staging_path(snapshots_dir: Path) -> Path:
    return _staging_dir(snapshots_dir) / STAGING_FILENAME


def _current_json(snapshots_dir: Path) -> Path:
    return snapshots_dir / CURRENT_FILENAME


def _snapshot_name(version: str) -> str:
    return f"{SNAPSHOT_PREFIX}{version}{SNAPSHOT_SUFFIX}"


def _content_hash(gold_dir: Path, tables: tuple[str, ...]) -> str:
    """SHA-256 (12 hex) sobre os Parquet Gold, em ordem estável.

    Determinístico: o mesmo Gold produz o mesmo hash. Entra no nome/versão do
    snapshot. O carimbo de tempo (que também compõe a versão) é o único
    não-determinismo, e é intencional (análogo ao _ingested_at da Bronze).
    """
    h = hashlib.sha256()
    for table in tables:
        parquet = gold_dir / table / f"{table}.parquet"
        h.update(table.encode("utf-8"))
        with open(parquet, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()[:12]


def _remove_staging(snapshots_dir: Path) -> None:
    """Remove o arquivo de staging e o eventual .wal deixado por run anterior."""
    staging = _staging_path(snapshots_dir)
    for p in (staging, staging.with_suffix(staging.suffix + ".wal")):
        if p.exists():
            p.unlink()


# ---------------------------------------------------------------------------
# 1. BUILD (staging) — carrega o Gold como tabelas físicas + metadados.
# ---------------------------------------------------------------------------


def build_staging(
    *,
    snapshots_dir: Path = SNAPSHOTS_DIR,
    gold_dir: Path = GOLD_DIR,
    tables: tuple[str, ...] = GOLD_SNAPSHOT_TABLES,
    log=None,
) -> StagingBuild:
    """Constrói o snapshot num arquivo temporário (nunca o que a API lê).

    Cria uma tabela física por tabela Gold via ``CREATE OR REPLACE TABLE ... AS
    SELECT * FROM read_parquet(...)`` (idempotente) e a tabela ``_snapshot_meta``.
    """
    staging_dir = _staging_dir(snapshots_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    _remove_staging(snapshots_dir)
    staging = _staging_path(snapshots_dir)

    built_at = dt.datetime.now(dt.UTC)
    content_hash = _content_hash(gold_dir, tables)
    version = f"{built_at.strftime('%Y%m%dT%H%M%SZ')}_{content_hash}"
    git_commit = git_commit_short()

    started = time.perf_counter()
    con = duckdb.connect(str(staging))
    try:
        for table in tables:
            parquet = (gold_dir / table / f"{table}.parquet").as_posix()
            con.execute(
                f"CREATE OR REPLACE TABLE {table} AS "
                f"SELECT * FROM read_parquet('{parquet}')"
            )
            if log:
                log.info("snapshot: carregada tabela %s", table)

        revenue_total = float(
            con.execute("SELECT SUM(basket_revenue) FROM fct_basket").fetchone()[0]
        )
        basket_count = int(con.execute("SELECT COUNT(*) FROM fct_basket").fetchone()[0])
        household_count = int(
            con.execute("SELECT COUNT(*) FROM agg_household_rfm").fetchone()[0]
        )

        # Tabela técnica de metadados do snapshot (proveniência + reconciliação).
        con.execute(
            f"""
            CREATE OR REPLACE TABLE {META_TABLE} (
                built_at         VARCHAR,  -- ISO-8601 UTC (sem ambiguidade de fuso)
                gold_source      VARCHAR,
                revenue_total    DOUBLE,
                basket_count     BIGINT,
                household_count  BIGINT,
                git_commit       VARCHAR,
                schema_version   VARCHAR,
                content_hash     VARCHAR,
                snapshot_version VARCHAR
            )
            """
        )
        con.execute(
            f"INSERT INTO {META_TABLE} VALUES (?,?,?,?,?,?,?,?,?)",
            [
                built_at.isoformat(timespec="seconds"),
                gold_dir.as_posix(),
                revenue_total,
                basket_count,
                household_count,
                git_commit,
                SCHEMA_VERSION,
                content_hash,
                version,
            ],
        )
        # CHECKPOINT força a mesclagem do WAL no arquivo principal, de modo que o
        # os.replace promova um único arquivo consistente (sem .wal pendente).
        con.execute("CHECKPOINT")
    finally:
        con.close()

    build_seconds = time.perf_counter() - started
    return StagingBuild(
        path=staging,
        version=version,
        built_at=built_at,
        content_hash=content_hash,
        revenue_total=revenue_total,
        basket_count=basket_count,
        household_count=household_count,
        git_commit=git_commit,
        build_seconds=build_seconds,
    )


# ---------------------------------------------------------------------------
# 2. VALIDAÇÃO (gate) — roda os checks sobre o staging, em read_only.
# ---------------------------------------------------------------------------


def validate_staging(
    staging_path: Path,
    *,
    checks: tuple[SnapshotCheck, ...] = VALIDATION_CHECKS,
) -> list[CheckOutcome]:
    """Avalia cada check no .duckdb em staging. Abre em read_only (prova de leitura).

    Não levanta por check reprovado; devolve os resultados para o chamador decidir
    (o gate está em :func:`publish_snapshot` / :func:`materialize_snapshot`).
    """
    outcomes: list[CheckOutcome] = []
    con = duckdb.connect(str(staging_path), read_only=True)
    try:
        for check in checks:
            try:
                observed = float(con.execute(check.sql).fetchone()[0])
                passed = check.evaluate(observed)
            except Exception:  # noqa: BLE001 — tabela ausente/SQL inválido = reprovado.
                observed = float("nan")
                passed = False
            outcomes.append(
                CheckOutcome(
                    name=check.name,
                    description=check.description,
                    passed=passed,
                    observed=observed,
                    expected=check.expected,
                    comparator=check.comparator,
                    tol=check.tol,
                )
            )
    finally:
        con.close()
    return outcomes


# ---------------------------------------------------------------------------
# 3. PUBLICAÇÃO ATÔMICA + ponteiro + retenção.
# ---------------------------------------------------------------------------


def _list_snapshots(snapshots_dir: Path) -> list[Path]:
    """Snapshots versionados existentes (mais recentes primeiro, por mtime)."""
    files = [
        p
        for p in snapshots_dir.glob(f"{SNAPSHOT_PREFIX}*{SNAPSHOT_SUFFIX}")
        if p.is_file()
    ]
    # Ordena por (mtime, nome) desc: mtime reflete a ordem de publicação; o nome
    # (timestamp + hash + sufixo) é o desempate determinístico se mtimes empatarem.
    return sorted(files, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def _apply_retention(
    snapshots_dir: Path, active_file: str, keep: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Mantém os ``keep`` snapshots mais recentes (nunca remove o ativo)."""
    snaps = _list_snapshots(snapshots_dir)
    retained: list[str] = []
    removed: list[str] = []
    for i, p in enumerate(snaps):
        if i < keep or p.name == active_file:
            retained.append(p.name)
        else:
            p.unlink()
            # Remove também um eventual .wal órfão do mesmo snapshot.
            wal = p.with_suffix(p.suffix + ".wal")
            if wal.exists():
                wal.unlink()
            removed.append(p.name)
    return tuple(retained), tuple(removed)


def publish_snapshot(
    build: StagingBuild,
    outcomes: list[CheckOutcome],
    *,
    snapshots_dir: Path = SNAPSHOTS_DIR,
    retention: int = RETENTION_COUNT,
    log=None,
) -> PublishResult:
    """Promove o staging validado. GATE: se algum check falhou, aborta e limpa.

    Publicação em duas trocas atômicas:
      1. ``os.replace(staging, snapshot_<versao>.duckdb)`` — move o arquivo.
      2. ``os.replace(current.json.tmp, current.json)`` — troca o ponteiro.
    """
    failed = [o for o in outcomes if not o.passed]
    if failed:
        # Gate: NÃO promove. Deixa o snapshot atual (se houver) intacto.
        _remove_staging(snapshots_dir)
        names = ", ".join(o.name for o in failed)
        if log:
            for o in failed:
                log.error(
                    "snapshot check REPROVADO %s: observado=%s esperado=%s",
                    o.name,
                    o.observed,
                    o.expected,
                )
        raise SnapshotValidationError(
            f"Validação do snapshot falhou ({len(failed)} check(s)): {names}. "
            "Publicação abortada; snapshot atual intacto."
        )

    active_file = _snapshot_name(build.version)
    active_path = snapshots_dir / active_file

    # 1. Move atômico do staging para o nome versionado final (mesmo volume).
    os.replace(build.path, active_path)
    size_bytes = active_path.stat().st_size
    published_at = dt.datetime.now(dt.UTC)

    # 2. Ponteiro current.json via arquivo temporário + troca atômica.
    payload = {
        "active": active_file,
        "version": build.version,
        "schema_version": SCHEMA_VERSION,
        "published_at": published_at.isoformat(timespec="seconds"),
        "built_at": build.built_at.isoformat(timespec="seconds"),
        "revenue_total": round(build.revenue_total, 2),
        "basket_count": build.basket_count,
        "household_count": build.household_count,
        "git_commit": build.git_commit,
        "content_hash": build.content_hash,
        "tables": list(GOLD_SNAPSHOT_TABLES),
        "checks": "passed",
    }
    current = _current_json(snapshots_dir)
    tmp = current.with_suffix(current.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, current)

    retained, removed = _apply_retention(snapshots_dir, active_file, retention)
    if log:
        log.info("snapshot publicado: %s (%s bytes)", active_file, f"{size_bytes:,}")
        if removed:
            log.info("snapshots removidos por retenção: %s", ", ".join(removed))

    return PublishResult(
        version=build.version,
        active_file=active_file,
        active_path=active_path,
        current_json=current,
        published_at=published_at,
        revenue_total=build.revenue_total,
        basket_count=build.basket_count,
        household_count=build.household_count,
        size_bytes=size_bytes,
        outcomes=tuple(outcomes),
        retained=retained,
        removed=removed,
    )


def read_current(snapshots_dir: Path = SNAPSHOTS_DIR) -> dict | None:
    """Lê o ponteiro ``current.json`` (contrato de leitura da API)."""
    current = _current_json(snapshots_dir)
    if not current.exists():
        return None
    return json.loads(current.read_text(encoding="utf-8"))


def materialize_snapshot(
    *,
    snapshots_dir: Path = SNAPSHOTS_DIR,
    gold_dir: Path = GOLD_DIR,
    tables: tuple[str, ...] = GOLD_SNAPSHOT_TABLES,
    checks: tuple[SnapshotCheck, ...] = VALIDATION_CHECKS,
    retention: int = RETENTION_COUNT,
    log=None,
) -> PublishResult:
    """Orquestra build -> validação (gate) -> publicação atômica. Levanta se falhar."""
    build = build_staging(
        snapshots_dir=snapshots_dir, gold_dir=gold_dir, tables=tables, log=log
    )
    outcomes = validate_staging(build.path, checks=checks)
    return publish_snapshot(
        build, outcomes, snapshots_dir=snapshots_dir, retention=retention, log=log
    )


# ---------------------------------------------------------------------------
# Asset Dagster: published_snapshot (grupo "snapshot"), depende do Gold.
# ---------------------------------------------------------------------------

_ASSET_KEY = AssetKey(["snapshot", "published_snapshot"])


def _structural_checks_on_published(result: PublishResult) -> list[AssetCheckResult]:
    """Avalia os 2 checks estruturais no arquivo PUBLICADO (não no staging)."""
    results: list[AssetCheckResult] = []

    # a) current.json aponta para um arquivo existente.
    current = read_current(result.current_json.parent)
    points_ok = bool(current) and (result.current_json.parent / current["active"]).exists()
    results.append(
        AssetCheckResult(
            check_name=CHECK_CURRENT_POINTS_TO_FILE,
            passed=points_ok,
            severity=AssetCheckSeverity.ERROR,
            metadata={
                "active": MetadataValue.text(current["active"] if current else "—"),
                "current_json": MetadataValue.path(str(result.current_json)),
            },
        )
    )

    # b) O snapshot abre em read_only e todas as tabelas Gold estão presentes.
    opens_ok = False
    n_tables = 0
    try:
        con = duckdb.connect(str(result.active_path), read_only=True)
        try:
            for t in GOLD_SNAPSHOT_TABLES:
                con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
            n_tables = len(GOLD_SNAPSHOT_TABLES)
            opens_ok = True
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        opens_ok = False
    results.append(
        AssetCheckResult(
            check_name=CHECK_OPENS_READ_ONLY,
            passed=opens_ok,
            severity=AssetCheckSeverity.ERROR,
            metadata={"tables_readable": MetadataValue.int(n_tables)},
        )
    )
    return results


def build_published_snapshot_asset() -> AssetsDefinition:
    """Fabrica o asset ``published_snapshot`` com todos os asset checks."""
    dep_keys = [AssetKey(["gold", t]) for t in GOLD_SNAPSHOT_TABLES]
    check_specs = [
        AssetCheckSpec(name=c.name, asset=_ASSET_KEY, description=c.description)
        for c in VALIDATION_CHECKS
    ]
    check_specs += [
        AssetCheckSpec(
            name=CHECK_CURRENT_POINTS_TO_FILE,
            asset=_ASSET_KEY,
            description="current.json aponta para um arquivo .duckdb existente.",
        ),
        AssetCheckSpec(
            name=CHECK_OPENS_READ_ONLY,
            asset=_ASSET_KEY,
            description="O snapshot publicado abre em read_only com todas as tabelas Gold.",
        ),
    ]

    @asset(
        name="published_snapshot",
        key_prefix="snapshot",
        group_name="snapshot",
        kinds={"duckdb"},
        deps=dep_keys,
        description=(
            "Snapshot DuckDB read-only consumido pela API: build em staging, "
            "validação das âncoras (gate) e publicação atômica via current.json."
        ),
        check_specs=check_specs,
    )
    def _published_snapshot(context):
        # 1. Build em staging (nunca escreve o arquivo que a API lê).
        build = build_staging(log=context.log)

        # 2. Validação ANTES de publicar (gate). Se falhar, publish_snapshot
        #    levanta SnapshotValidationError e NÃO promove — snapshot atual intacto.
        outcomes = validate_staging(build.path)
        try:
            result = publish_snapshot(build, outcomes, log=context.log)
        except SnapshotValidationError:
            # Falha dura: aborta a materialização (nada publicado).
            raise

        # 3. Metadados de materialização.
        yield MaterializeResult(
            metadata={
                "published_version": MetadataValue.text(result.version),
                "active_file": MetadataValue.text(result.active_file),
                "active_path": MetadataValue.path(str(result.active_path)),
                "current_json": MetadataValue.path(str(result.current_json)),
                "revenue_total": MetadataValue.float(round(result.revenue_total, 2)),
                "basket_count": MetadataValue.int(result.basket_count),
                "household_count": MetadataValue.int(result.household_count),
                "n_tables": MetadataValue.int(len(GOLD_SNAPSHOT_TABLES)),
                "snapshot_size_bytes": MetadataValue.int(result.size_bytes),
                "build_seconds": MetadataValue.float(round(build.build_seconds, 3)),
                "git_commit": MetadataValue.text(build.git_commit),
                "retained_snapshots": MetadataValue.text(", ".join(result.retained)),
                "published_at": MetadataValue.text(
                    result.published_at.isoformat(timespec="seconds")
                ),
            }
        )

        # 4. Asset checks: reconciliações (do staging, já aprovadas) + estruturais.
        for o in result.outcomes:
            yield AssetCheckResult(
                check_name=o.name,
                passed=o.passed,
                severity=AssetCheckSeverity.ERROR,
                metadata={
                    "observed": MetadataValue.float(float(round(o.observed, 4))),
                    "expected": MetadataValue.float(float(round(o.expected, 4))),
                    "comparator": MetadataValue.text(o.comparator),
                    "tolerance": MetadataValue.float(float(o.tol)),
                },
            )
        yield from _structural_checks_on_published(result)

    return _published_snapshot
