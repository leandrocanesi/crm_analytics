"""Testes de contrato dos endpoints de retenção (metrics.md §6).

Reconciliam com as âncoras do snapshot real:
  12 meses · retenção Jan→Fev ≈ 0,8885 · 12 coortes ·
  soma dos cohort_size distintos == 2.469 (= domicílios) · months_since=0 → 1.0.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

HOUSEHOLD_ANCHOR = 2_469
N_MONTHS = 12
N_COHORTS = 12
AS_OF = "2018-01-01"


def test_retention_monthly_contract(client: TestClient) -> None:
    r = client.get("/retention/monthly")
    assert r.status_code == 200
    body = r.json()
    assert body["as_of_date"] == AS_OF
    assert body["n_months"] == N_MONTHS
    assert len(body["series"]) == N_MONTHS
    assert "note" in body and body["note"]

    series = body["series"]
    # Todas as taxas em [0,1].
    assert all(0.0 <= p["retention_rate"] <= 1.0 for p in series)
    # Série ordenada por activity_month ASC.
    months = [p["activity_month"] for p in series]
    assert months == sorted(months)
    assert months[0] == "2017-01-01"
    assert months[-1] == "2017-12-01"

    # Contrato completo de cada ponto.
    assert set(series[0]) == {
        "activity_month",
        "active_households",
        "retained_next_month",
        "retention_rate",
        "next_month_partial",
    }

    # Retenção Jan → Fev ≈ 0,8885 (âncora do snapshot real).
    jan = series[0]
    assert jan["activity_month"] == "2017-01-01"
    assert jan["retention_rate"] == pytest.approx(0.8885, abs=1e-4)

    # Só o mês-fronteira (2017-12) é parcial; os demais são completos.
    dec = series[-1]
    assert dec["activity_month"] == "2017-12-01"
    assert dec["next_month_partial"] is True
    assert all(p["next_month_partial"] is False for p in series[:-1])


def test_retention_cohorts_contract(client: TestClient) -> None:
    r = client.get("/retention/cohorts")
    assert r.status_code == 200
    body = r.json()
    assert body["as_of_date"] == AS_OF
    assert body["n_cohorts"] == N_COHORTS
    assert len(body["cohorts"]) == N_COHORTS
    assert "note" in body and body["note"]
    # A ressalva de left-censoring precisa estar explícita (metrics.md §6.3).
    assert "censoring" in body["note"].lower()

    cohorts = body["cohorts"]
    # Soma dos tamanhos de coorte (cada domicílio em exatamente uma) == universo.
    assert sum(c["cohort_size"] for c in cohorts) == HOUSEHOLD_ANCHOR

    # Coortes ordenadas por cohort_month ASC.
    cohort_months = [c["cohort_month"] for c in cohorts]
    assert cohort_months == sorted(cohort_months)
    assert cohort_months[0] == "2017-01-01"

    for c in cohorts:
        points = c["points"]
        assert points, "toda coorte tem ao menos o ponto months_since=0"
        # points ordenados por months_since ASC.
        ms = [p["months_since"] for p in points]
        assert ms == sorted(ms)
        # O primeiro ponto é o próprio mês da coorte: months_since=0, taxa=1.0.
        first = points[0]
        assert first["months_since"] == 0
        assert first["retention_rate"] == pytest.approx(1.0, abs=1e-9)
        assert first["activity_month"] == c["cohort_month"]
        # Todas as taxas em [0,1].
        assert all(0.0 <= p["retention_rate"] <= 1.0 for p in points)
        # Contrato completo de cada ponto.
        assert set(first) == {
            "months_since",
            "activity_month",
            "active_households",
            "retention_rate",
        }
