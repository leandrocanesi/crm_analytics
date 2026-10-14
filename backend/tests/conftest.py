"""Fixtures de teste. Exercita a API contra o snapshot REAL publicado.

Não há mock do DuckDB: os testes de contrato só têm valor se reconciliarem com as
âncoras do snapshot de verdade (receita 4.596.039,58; 155.848 cestas; 2.469
domicílios). Se não houver snapshot publicado, os testes são pulados com aviso.
"""

from __future__ import annotations

import pytest
from app.deps import get_snapshot
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def _require_snapshot() -> None:
    """Pula toda a suíte de contrato se não houver snapshot publicado."""
    if not get_snapshot().available():
        pytest.skip(
            "Nenhum snapshot publicado em data/snapshots/ — materialize o pipeline "
            "Dagster (snapshot/published_snapshot) antes de rodar os testes de contrato.",
            allow_module_level=True,
        )
