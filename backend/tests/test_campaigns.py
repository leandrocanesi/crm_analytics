"""Testes de contrato dos endpoints de campanha/cupom (metrics.md §8, factual 8.1–8.4).

Reconciliam com as âncoras do snapshot real (metrics.md §8.0.1):
  27 campanhas · 1.559 domicílios expostos (63,1% de 2.469) · 410 resgataram ·
  2.102 eventos de resgate · tipos A/B/C · toda taxa ∈ [0,1].
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

UNIVERSE = 2_469
N_CAMPAIGNS = 27
EXPOSED_TOTAL = 1_559
REDEMPTION_EVENTS = 2_102
AS_OF = "2018-01-01"


def test_campaign_performance_contract(client: TestClient) -> None:
    r = client.get("/campaigns/performance")
    assert r.status_code == 200
    body = r.json()
    assert body["as_of_date"] == AS_OF
    assert body["n_campaigns"] == N_CAMPAIGNS
    assert body["universe_households"] == UNIVERSE
    assert body["households_exposed_total"] == EXPOSED_TOTAL
    assert "note" in body and body["note"]

    campaigns = body["campaigns"]
    assert len(campaigns) == N_CAMPAIGNS
    # Toda taxa em [0,1] e numerador ⊆ denominador (resgatadores ⊆ expostos).
    for c in campaigns:
        assert 0.0 <= c["redemption_rate"] <= 1.0
        assert c["households_redeemed"] <= c["households_exposed"]
    # Alcance NÃO é aditivo: a soma por campanha > universo distinto alcançado.
    assert sum(c["households_exposed"] for c in campaigns) > EXPOSED_TOTAL
    # Ordenado por households_exposed DESC.
    exposed = [c["households_exposed"] for c in campaigns]
    assert exposed == sorted(exposed, reverse=True)
    # Contrato completo de cada item.
    assert set(campaigns[0]) == {
        "campaign_id",
        "campaign_type",
        "start_date",
        "end_date",
        "households_exposed",
        "households_redeemed",
        "redemption_rate",
    }
    # Datas como string ISO YYYY-MM-DD.
    assert len(campaigns[0]["start_date"]) == 10
    assert campaigns[0]["start_date"][4] == "-"


def test_campaign_by_type_contract(client: TestClient) -> None:
    r = client.get("/campaigns/by-type")
    assert r.status_code == 200
    body = r.json()
    assert body["as_of_date"] == AS_OF
    assert "note" in body and body["note"]
    # A ressalva crítica de não-aditividade precisa estar explícita (§8.0.2).
    assert "aditiv" in body["note"].lower()

    types = body["types"]
    assert len(types) == 3
    assert {t["campaign_type"] for t in types} == {"Type A", "Type B", "Type C"}
    # SOMENTE os eventos são aditivos: somam 2.102.
    assert sum(t["n_redemption_events"] for t in types) == REDEMPTION_EVENTS
    # n_campaigns por tipo soma 27.
    assert sum(t["n_campaigns"] for t in types) == N_CAMPAIGNS
    # Expostos NÃO são aditivos (soma > distintos do painel).
    assert sum(t["households_exposed"] for t in types) > EXPOSED_TOTAL
    # Toda taxa em [0,1].
    assert all(0.0 <= t["redemption_rate"] <= 1.0 for t in types)
    # Ordenado por campaign_type ASC.
    labels = [t["campaign_type"] for t in types]
    assert labels == sorted(labels)
    assert set(types[0]) == {
        "campaign_type",
        "n_campaigns",
        "households_exposed",
        "n_redemption_events",
        "households_redeemed",
        "n_coupons_redeemed",
        "redemption_rate",
    }


def test_campaign_overlap_contract(client: TestClient) -> None:
    r = client.get("/campaigns/overlap")
    assert r.status_code == 200
    body = r.json()
    assert body["as_of_date"] == AS_OF
    assert body["total_exposed"] == EXPOSED_TOTAL
    assert body["universe"] == UNIVERSE
    assert body["exposure_rate"] == pytest.approx(0.631, abs=1e-3)
    assert body["max_campaigns_per_household"] == 15
    assert body["avg_campaigns_per_household"] == pytest.approx(4.23, abs=1e-2)
    assert "note" in body and body["note"]

    dist = body["distribution"]
    # Histograma soma exatamente os domicílios expostos.
    assert sum(b["n_households"] for b in dist) == EXPOSED_TOTAL
    # Ordenado por n_campaigns_exposed ASC, começando em 1.
    bins = [b["n_campaigns_exposed"] for b in dist]
    assert bins == sorted(bins)
    assert bins[0] == 1
    assert bins[-1] == 15
    assert set(dist[0]) == {"n_campaigns_exposed", "n_households"}
