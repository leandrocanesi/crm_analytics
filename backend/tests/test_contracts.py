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


def test_rfm_households_sem_filtro(client: TestClient) -> None:
    r = client.get("/rfm/households")
    assert r.status_code == 200
    body = r.json()
    # total ignora paginação: reconcilia o universo de domicílios.
    assert body["total"] == HOUSEHOLD_ANCHOR
    assert body["segment"] is None
    assert body["limit"] == 50
    assert body["offset"] == 0
    # A página respeita o limit.
    assert len(body["households"]) <= body["limit"]
    assert len(body["households"]) == 50
    assert body["as_of_date"] == AS_OF
    assert body["currency"] == "USD"
    # Cada domicílio traz o contrato completo.
    first = body["households"][0]
    assert set(first) == {
        "household_id",
        "recency_days",
        "frequency_baskets",
        "monetary_value",
        "r_score",
        "f_score",
        "m_score",
        "rfm_segment",
    }


def test_rfm_households_filtro_por_segmento(client: TestClient) -> None:
    r = client.get("/rfm/households", params={"segment": "Campeões", "limit": 200})
    assert r.status_code == 200
    body = r.json()
    # Total de Campeões no universo (contagem do snapshot real).
    assert body["total"] == 522
    assert body["segment"] == "Campeões"
    # Todos os retornados pertencem ao segmento filtrado.
    assert all(h["rfm_segment"] == "Campeões" for h in body["households"])
    assert len(body["households"]) == 200  # limit teto


def test_rfm_households_ordenacao_desc_monetary(client: TestClient) -> None:
    r = client.get(
        "/rfm/households",
        params={"sort_by": "monetary_value", "order": "desc", "limit": 100},
    )
    assert r.status_code == 200
    values = [h["monetary_value"] for h in r.json()["households"]]
    # Desc: não-crescente; primeiro >= último.
    assert values == sorted(values, reverse=True)
    assert values[0] >= values[-1]


def test_rfm_households_ordenacao_asc_recency(client: TestClient) -> None:
    r = client.get(
        "/rfm/households", params={"sort_by": "recency_days", "order": "asc"}
    )
    assert r.status_code == 200
    values = [h["recency_days"] for h in r.json()["households"]]
    assert values == sorted(values)


def test_rfm_households_paginacao_estavel(client: TestClient) -> None:
    # Desempate por household_id → páginas não se sobrepõem.
    p1 = client.get("/rfm/households", params={"limit": 50, "offset": 0}).json()
    p2 = client.get("/rfm/households", params={"limit": 50, "offset": 50}).json()
    ids1 = {h["household_id"] for h in p1["households"]}
    ids2 = {h["household_id"] for h in p2["households"]}
    assert ids1.isdisjoint(ids2)


def test_rfm_households_segmento_invalido_422(client: TestClient) -> None:
    r = client.get("/rfm/households", params={"segment": "Baleias"})
    assert r.status_code == 422


def test_rfm_households_limit_acima_do_teto_422(client: TestClient) -> None:
    # Decisão: limit > 200 é REJEITADO (422), não clampado silenciosamente.
    r = client.get("/rfm/households", params={"limit": 201})
    assert r.status_code == 422


def test_rfm_households_sort_by_invalido_422(client: TestClient) -> None:
    r = client.get("/rfm/households", params={"sort_by": "household_id"})
    assert r.status_code == 422


def test_openapi_available(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for path in (
        "/health",
        "/meta",
        "/overview",
        "/revenue/weekly",
        "/rfm/segments",
        "/rfm/households",
        "/retention/monthly",
        "/retention/cohorts",
    ):
        assert path in paths
        # Contrato read-only: cada endpoint só expõe GET.
        assert set(paths[path].keys()) == {"get"}
