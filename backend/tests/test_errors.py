"""Teste do caminho de erro: snapshot indisponível → HTTP 503 tipado.

Prova o handler de erro centralizado sem depender do snapshot real: substitui a
dependência ``get_snapshot`` por um manager apontando para um diretório vazio.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.deps import get_snapshot
from app.main import app
from app.snapshot import SnapshotManager
from fastapi.testclient import TestClient


@pytest.fixture
def client_sem_snapshot(tmp_path: Path):
    empty = SnapshotManager(tmp_path)  # diretório vazio: sem current.json
    app.dependency_overrides[get_snapshot] = lambda: empty
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health_reporta_indisponivel(client_sem_snapshot: TestClient) -> None:
    r = client_sem_snapshot.get("/health")
    # /health não quebra: responde 200 e sinaliza a ausência no corpo.
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["snapshot_available"] is False
    assert body["snapshot_version"] is None


@pytest.mark.parametrize(
    "path", ["/meta", "/overview", "/revenue/weekly", "/rfm/segments"]
)
def test_endpoints_de_dados_retornam_503(
    client_sem_snapshot: TestClient, path: str
) -> None:
    r = client_sem_snapshot.get(path)
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "snapshot_unavailable"
    assert "snapshot" in body["detail"].lower()
