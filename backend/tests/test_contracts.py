"""Testes de contrato dos endpoints — reconciliam com as âncoras do snapshot.

Âncoras (metrics.md §0 / snapshots.md §4):
  receita == 4.596.039,58 · cestas == 155.848 · domicílios == 2.469 ·
  53 semanas · ticket médio ≈ 29,49 · 7 segmentos RFM.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

REVENUE_ANCHOR = 4_596_039.58
BASKET_ANCHOR = 155_848
HOUSEHOLD_ANCHOR = 2_469
N_WEEKS = 53
AS_OF = "2018-01-01"


def test_health_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["snapshot_available"] is True
    assert body["snapshot_version"]
    assert body["schema_version"] == "1"


def test_meta_anchors(client: TestClient) -> None:
    r = client.get("/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "1"
    assert body["as_of_date"] == AS_OF
    assert body["revenue_total"] == pytest.approx(REVENUE_ANCHOR, abs=0.01)
    assert body["basket_count"] == BASKET_ANCHOR
    assert body["household_count"] == HOUSEHOLD_ANCHOR
    assert body["currency"] == "USD"
    assert body["snapshot_version"]
    assert body["git_commit"]
    assert set(body["tables"]) >= {
        "fct_basket",
        "agg_weekly_revenue",
        "agg_household_rfm",
        "agg_household_activity_month",
    }


def test_overview_cards(client: TestClient) -> None:
    r = client.get("/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["total_revenue"] == pytest.approx(REVENUE_ANCHOR, abs=0.01)
    assert body["n_baskets"] == BASKET_ANCHOR
    assert body["n_active_households"] == HOUSEHOLD_ANCHOR
    assert body["household_universe"] == HOUSEHOLD_ANCHOR
    # Ticket médio por cesta ≈ 29,49 (metrics.md §4) — jamais ~3,13 (grão de linha).
    assert body["avg_basket_value"] == pytest.approx(29.49, abs=0.01)
    assert body["as_of_date"] == AS_OF


def test_weekly_revenue_series(client: TestClient) -> None:
    r = client.get("/revenue/weekly")
    assert r.status_code == 200
    body = r.json()
    assert body["n_weeks"] == N_WEEKS
    assert len(body["series"]) == N_WEEKS
    # Soma da série reconcilia a âncora de receita.
    assert body["total_revenue"] == pytest.approx(REVENUE_ANCHOR, abs=0.01)
    assert sum(p["revenue"] for p in body["series"]) == pytest.approx(
        REVENUE_ANCHOR, abs=0.01
    )
    # Soma de cestas reconcilia 155.848.
    assert sum(p["n_baskets"] for p in body["series"]) == BASKET_ANCHOR
    # Série ordenada por semana, 1..53.
    weeks = [p["week"] for p in body["series"]]
    assert weeks == sorted(weeks)
    assert weeks[0] == 1 and weeks[-1] == N_WEEKS


def test_rfm_segments_distribution(client: TestClient) -> None:
    r = client.get("/rfm/segments")
    assert r.status_code == 200
    body = r.json()
    assert body["n_households_total"] == HOUSEHOLD_ANCHOR
    assert sum(s["n_households"] for s in body["segments"]) == HOUSEHOLD_ANCHOR
    assert body["n_segments"] == 7
    assert len(body["segments"]) == 7
    # Monetário reconcilia a âncora de receita (M é partição exata da receita).
    assert sum(s["monetary_value"] for s in body["segments"]) == pytest.approx(
        REVENUE_ANCHOR, abs=0.01
    )
    # Shares somam ~1.
    assert sum(s["household_share"] for s in body["segments"]) == pytest.approx(
        1.0, abs=0.01
    )
    # Ordenado por nº de domicílios (desc).
    counts = [s["n_households"] for s in body["segments"]]
    assert counts == sorted(counts, reverse=True)


def test_openapi_available(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for path in ("/health", "/meta", "/overview", "/revenue/weekly", "/rfm/segments"):
        assert path in paths
        # Contrato read-only: cada endpoint só expõe GET.
        assert set(paths[path].keys()) == {"get"}
