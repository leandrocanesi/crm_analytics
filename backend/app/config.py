"""Configuração da API via Pydantic Settings (pydantic-settings).

Lê variáveis de ambiente (e, se existir, um ``.env`` na raiz do monorepo ou em
``backend/``). O ponto crítico: a API aponta para o **DIRETÓRIO de snapshots**, não
para um arquivo fixo. O arquivo ``.duckdb`` ativo é resolvido em runtime via
``data/snapshots/current.json`` (ver ``docs/snapshots.md`` §7 e ``snapshot.py``).

Decisão: ``SNAPSHOTS_DIR`` (diretório) substitui o antigo ``SNAPSHOT_DB_PATH``
(arquivo), que estava errado — apontar para ``current.duckdb`` ignoraria a troca
atômica de versão (blue-green) feita pelo pipeline.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> app -> backend -> raiz do monorepo.
# Resolvido a partir do arquivo (não do cwd), pois threads/CLI podem mudar o cwd.
APP_DIR: Path = Path(__file__).resolve().parent
BACKEND_DIR: Path = APP_DIR.parent
REPO_ROOT: Path = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Configuração tipada da API. Valores vêm de env vars / arquivo .env."""

    model_config = SettingsConfigDict(
        # Procura .env na raiz do monorepo e em backend/ (o segundo tem prioridade).
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_title: str = "Customer Intelligence Lab API"
    api_version: str = "0.1.0"

    # Origens permitidas para CORS (lista separada por vírgula).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Diretório onde o pipeline publica os snapshots + current.json.
    # Relativo é resolvido a partir de backend/ (convenção "../data/snapshots").
    snapshots_dir: str = "../data/snapshots"

    # schema_version do contrato de snapshot que esta API entende (recusa outras).
    schema_version_supported: str = "1"

    # Data de referência (as-of) FIXA do dataset — NUNCA a data de hoje
    # (CLAUDE.md regra 8 / metrics.md §0). Fim da semana 53 = 2018-01-01.
    as_of_date: str = "2018-01-01"

    # Moeda dos valores monetários (receita da AMOSTRA do painel, não da rede).
    currency: str = "USD"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def snapshots_path(self) -> Path:
        """Caminho absoluto do diretório de snapshots.

        Caminho relativo é resolvido a partir de ``backend/`` (assim
        ``"../data/snapshots"`` cai em ``<repo>/data/snapshots``).
        """
        p = Path(self.snapshots_dir)
        if not p.is_absolute():
            p = (BACKEND_DIR / p).resolve()
        return p


@lru_cache
def get_settings() -> Settings:
    """Settings em cache (singleton de processo)."""
    return Settings()
