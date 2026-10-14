"""Configuração estática da publicação de snapshot DuckDB.

O snapshot é o **artefato read-only** que a API FastAPI vai consumir: um único
arquivo ``.duckdb`` com as tabelas Gold materializadas como tabelas físicas, mais
uma tabela de metadados (``_snapshot_meta``). O Dagster é o **único escritor**
(CLAUDE.md regra 6); a API apenas abre o arquivo apontado por ``current.json`` em
``read_only=True``. Ver ``docs/snapshots.md`` para a estratégia completa.

Tudo aqui é determinístico (sem leitura de relógio nem estado externo) para manter
a configuração reprodutível. O único não-determinismo *por design* é o carimbo de
tempo no nome/metadados do snapshot — análogo ao ``_ingested_at`` da Bronze.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import (
    BASKET_ANCHOR,
    GOLD_DIR,
    HOUSEHOLD_UNIVERSE,
    REPO_ROOT,
    REVENUE_ANCHOR_TOL_USD,
    REVENUE_ANCHOR_USD,
)

# ---------------------------------------------------------------------------
# Caminhos (derivados de REPO_ROOT, sem depender do cwd).
# ---------------------------------------------------------------------------
SNAPSHOTS_DIR = REPO_ROOT / "data" / "snapshots"
# Subpasta de build; nunca é lida pela API. O arquivo final validado é promovido
# para fora dela com os.replace (atômico no mesmo volume).
STAGING_DIRNAME = ".staging"
STAGING_FILENAME = "snapshot.duckdb.tmp"
CURRENT_FILENAME = "current.json"
SNAPSHOT_PREFIX = "snapshot_"
SNAPSHOT_SUFFIX = ".duckdb"

# Versão do schema do snapshot (contrato com a API). Incremente ao mudar a forma
# das tabelas publicadas; a API pode recusar versões que não entende.
SCHEMA_VERSION = "1"

# Retenção: nº de snapshots mantidos em disco para rollback. Os mais antigos
# (exceto o ativo) são removidos após uma publicação bem-sucedida.
RETENTION_COUNT = 3

# ---------------------------------------------------------------------------
# Tabelas Gold publicadas no snapshot (fonte = data/processed/gold/).
# A ordem é estável (entra no hash de conteúdo e nos metadados).
# ---------------------------------------------------------------------------
GOLD_SNAPSHOT_TABLES: tuple[str, ...] = (
    "fct_basket",
    "agg_weekly_revenue",
    "agg_household_rfm",
    "agg_household_activity_month",
    "agg_retention_monthly",
    "agg_cohort_retention",
)

# Nome da tabela técnica de metadados dentro do .duckdb.
META_TABLE = "_snapshot_meta"


def gold_parquet_path(table: str) -> str:
    """Caminho POSIX do Parquet Gold (arquivo único) de uma tabela."""
    return (GOLD_DIR / table / f"{table}.parquet").as_posix()


# ---------------------------------------------------------------------------
# Checks de validação (gate ANTES de publicar). Rodam sobre o .duckdb em staging.
# Se QUALQUER check falhar, a publicação é abortada e o snapshot atual fica
# intacto (docs/snapshots.md §4). Reproduzem as mesmas âncoras da Gold para provar
# que o snapshot carregou os dados corretos (sem perda nem fan-out).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotCheck:
    """Validação de um escalar agregado dentro do snapshot em staging.

    Executa ``sql`` (que deve retornar um único escalar) e compara com
    ``expected``:
      - ``comparator == "eq"``: passa se ``abs(observado - expected) <= tol``;
      - ``comparator == "ge"``: passa se ``observado >= expected`` (ex. não-vazio).
    """

    name: str
    description: str
    sql: str
    expected: float
    tol: float = 0.0
    comparator: str = "eq"  # "eq" | "ge"

    def evaluate(self, observed: float) -> bool:
        if self.comparator == "ge":
            return observed >= self.expected
        return abs(observed - self.expected) <= self.tol


# Presença + não-vazio de cada tabela (SELECT COUNT(*) ... >= 1). Se a tabela não
# existir, a query lança e a validação falha — exatamente o que queremos (gate).
_PRESENCE_CHECKS: tuple[SnapshotCheck, ...] = tuple(
    SnapshotCheck(
        name=f"{t}_present_non_empty",
        description=f"Tabela `{t}` existe e tem >= 1 linha.",
        sql=f"SELECT COUNT(*) FROM {t}",
        expected=1,
        comparator="ge",
    )
    for t in GOLD_SNAPSHOT_TABLES
)

# Reconciliações de receita e contagem (as âncoras do projeto).
_RECONCILE_CHECKS: tuple[SnapshotCheck, ...] = (
    SnapshotCheck(
        name="fct_basket_revenue_reconciles",
        description="SUM(fct_basket.basket_revenue) == âncora US$ 4.596.039,58.",
        sql="SELECT SUM(basket_revenue) FROM fct_basket",
        expected=REVENUE_ANCHOR_USD,
        tol=REVENUE_ANCHOR_TOL_USD,
    ),
    SnapshotCheck(
        name="weekly_revenue_reconciles",
        description="SUM(agg_weekly_revenue.revenue) == âncora US$ 4.596.039,58.",
        sql="SELECT SUM(revenue) FROM agg_weekly_revenue",
        expected=REVENUE_ANCHOR_USD,
        tol=REVENUE_ANCHOR_TOL_USD,
    ),
    SnapshotCheck(
        name="rfm_monetary_reconciles",
        description="SUM(agg_household_rfm.monetary_value) == âncora US$ 4.596.039,58.",
        sql="SELECT SUM(monetary_value) FROM agg_household_rfm",
        expected=REVENUE_ANCHOR_USD,
        tol=REVENUE_ANCHOR_TOL_USD,
    ),
    SnapshotCheck(
        name="basket_count_matches",
        description="COUNT(*) fct_basket == 155.848 cestas.",
        sql="SELECT COUNT(*) FROM fct_basket",
        expected=float(BASKET_ANCHOR),
        tol=0.0,
    ),
    SnapshotCheck(
        name="household_count_matches",
        description="COUNT(*) agg_household_rfm == 2.469 domicílios.",
        sql="SELECT COUNT(*) FROM agg_household_rfm",
        expected=float(HOUSEHOLD_UNIVERSE),
        tol=0.0,
    ),
)

VALIDATION_CHECKS: tuple[SnapshotCheck, ...] = _PRESENCE_CHECKS + _RECONCILE_CHECKS

# Nomes dos dois asset checks estruturais extra (avaliados no arquivo PUBLICADO).
CHECK_CURRENT_POINTS_TO_FILE = "current_json_points_to_existing_file"
CHECK_OPENS_READ_ONLY = "snapshot_opens_read_only"


def git_commit_short(repo_root=REPO_ROOT) -> str:
    """Short hash do commit atual, ou ``"unknown"`` fora de um repo git.

    Usado só como metadado de proveniência; nunca entra em check de validação.
    """
    import subprocess  # noqa: PLC0415 — import local: só usado aqui.

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001 — proveniência é best-effort.
        return "unknown"
