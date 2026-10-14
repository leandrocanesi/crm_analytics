"""Injeção de dependências da API (FastAPI ``Depends``).

O ``SnapshotManager`` é um singleton de processo (uma conexão read-only reusada,
com hot-swap interno quando o ponteiro muda). Em testes, pode ser substituído via
``app.dependency_overrides``.
"""

from __future__ import annotations

from functools import lru_cache

from .config import Settings, get_settings
from .snapshot import SnapshotManager


@lru_cache
def get_snapshot() -> SnapshotManager:
    settings: Settings = get_settings()
    return SnapshotManager(
        settings.snapshots_path,
        supported_schema=settings.schema_version_supported,
    )
