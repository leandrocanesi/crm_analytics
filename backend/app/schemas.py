"""Contratos de resposta (Pydantic) — tipados, estáveis e versionáveis.

Estes modelos são o contrato público da API (documentado no OpenAPI em /docs).
Mudá-los é uma decisão consciente (quebra o frontend). Valores monetários são
``float`` em USD e representam a receita da **AMOSTRA de domicílios do painel**
84.51°/dunnhumby — NÃO o faturamento da rede (metrics.md §0.1).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# Aviso de escopo reaproveitado nas respostas monetárias (metrics.md §0.1).
SAMPLE_NOTE = (
    "Receita observada da amostra de ~2.469 domicílios de fidelidade do painel "
    "84.51°/dunnhumby — NÃO é o faturamento total da rede."
)


class ErrorResponse(BaseModel):
    """Corpo de erro tipado (ex.: 503 quando o snapshot está indisponível)."""

    status: str = Field(description="Código curto do erro, ex.: 'snapshot_unavailable'.")
    detail: str = Field(description="Mensagem legível explicando a causa.")


class HealthResponse(BaseModel):
    """Healthcheck: a API está de pé e enxerga um snapshot válido?"""

    status: str = Field(description="'ok' se a API respondeu.")
    snapshot_available: bool = Field(
        description="True se há um snapshot publicado válido para ler."
    )
    snapshot_version: str | None = Field(
        default=None, description="Versão do snapshot ativo (do current.json), se houver."
    )
    schema_version: str | None = Field(
        default=None, description="schema_version do snapshot ativo, se houver."
    )


class MetaResponse(BaseModel):
    """Metadados do snapshot ativo: proveniência + âncoras de reconciliação."""

    schema_version: str = Field(description="Versão do contrato de snapshot.")
    snapshot_version: str = Field(description="Identificador da versão publicada.")
    built_at: str = Field(description="Quando o snapshot foi construído (ISO-8601 UTC).")
    published_at: str | None = Field(
        default=None, description="Quando o ponteiro passou a apontar para ele."
    )
    as_of_date: str = Field(
        description="Data de referência (as-of) FIXA do dataset — nunca 'hoje'."
    )
    revenue_total: float = Field(description="Receita observada total (âncora).")
    basket_count: int = Field(description="Nº de cestas (âncora = 155.848).")
    household_count: int = Field(description="Nº de domicílios (âncora = 2.469).")
    currency: str = Field(description="Moeda dos valores monetários.")
    git_commit: str = Field(description="Commit do repositório que gerou o snapshot.")
    content_hash: str = Field(description="Hash determinístico do conteúdo Gold.")
    tables: list[str] = Field(description="Tabelas publicadas no snapshot.")
    note: str = Field(default=SAMPLE_NOTE, description="Escopo da receita (amostra).")


class OverviewResponse(BaseModel):
    """Cards do topo do Overview (headline do painel)."""

    total_revenue: float = Field(description="Receita observada total da amostra (USD).")
    n_active_households: int = Field(
        description="Domicílios distintos com >= 1 cesta no período."
    )
    household_universe: int = Field(
        description="Universo de domicílios do painel (2.469)."
    )
    n_baskets: int = Field(description="Nº de cestas (tickets) no período.")
    avg_basket_value: float = Field(
        description="Ticket médio POR CESTA = receita / cestas (metrics.md §4)."
    )
    as_of_date: str = Field(description="Data de referência (as-of) do dataset.")
    currency: str = Field(description="Moeda dos valores monetários.")
    note: str = Field(default=SAMPLE_NOTE, description="Escopo da receita (amostra).")


class WeeklyRevenuePoint(BaseModel):
    """Um ponto da série semanal (grão = semana ISO do dataset, 1..53)."""

    week: int = Field(description="Número da semana no dataset (1..53).")
    revenue: float = Field(description="Receita observada na semana (USD).")
    n_baskets: int = Field(description="Nº de cestas na semana.")
    n_active_households: int = Field(
        description="Domicílios distintos ativos na semana (não-aditivo entre semanas)."
    )
    avg_basket_value: float = Field(
        description="Ticket médio da semana = revenue / n_baskets."
    )


class WeeklyRevenueResponse(BaseModel):
    """Série temporal de receita semanal para o gráfico do Overview."""

    as_of_date: str = Field(description="Data de referência (as-of) do dataset.")
    currency: str = Field(description="Moeda dos valores monetários.")
    n_weeks: int = Field(description="Nº de semanas na série (esperado 53).")
    total_revenue: float = Field(
        description="Soma da série (reconcilia a âncora de receita)."
    )
    series: list[WeeklyRevenuePoint] = Field(description="Pontos ordenados por semana.")
    note: str = Field(default=SAMPLE_NOTE, description="Escopo da receita (amostra).")


class RfmSegment(BaseModel):
    """Um segmento RFM nomeado (metrics.md §5.2)."""

    segment: str = Field(description="Nome do segmento (ex.: 'Campeões').")
    n_households: int = Field(description="Domicílios no segmento.")
    household_share: float = Field(
        description="Fração dos 2.469 domicílios neste segmento (0..1)."
    )
    monetary_value: float = Field(
        description="Soma do valor monetário (M) dos domicílios do segmento (USD)."
    )
    monetary_share: float = Field(
        description="Fração da receita total concentrada neste segmento (0..1)."
    )


class RfmSegmentsResponse(BaseModel):
    """Distribuição dos segmentos RFM para o Overview."""

    as_of_date: str = Field(description="Data de referência (as-of) do dataset.")
    currency: str = Field(description="Moeda dos valores monetários.")
    n_segments: int = Field(description="Nº de segmentos distintos (esperado 7).")
    n_households_total: int = Field(
        description="Total de domicílios (reconcilia a âncora = 2.469)."
    )
    segments: list[RfmSegment] = Field(
        description="Segmentos ordenados por nº de domicílios (desc)."
    )
    note: str = Field(default=SAMPLE_NOTE, description="Escopo da receita (amostra).")


# --- RFM detalhado (por domicílio) ---------------------------------------------
# Enums = allow-list de valores aceitos nos query params. O FastAPI valida contra
# estes valores e devolve 422 para qualquer coisa fora da lista (CLAUDE.md regra 7:
# nada vindo do cliente é interpolado livre no SQL).


class RfmSegmentName(StrEnum):
    """Os 7 segmentos RFM nomeados (metrics.md §5.2) — valores EXATOS para filtro."""

    CAMPEOES = "Campeões"
    LEAIS = "Leais"
    POTENCIAIS = "Potenciais"
    NOVOS = "Novos"
    EM_RISCO = "Em risco"
    HIBERNANDO_PERDIDOS = "Hibernando / Perdidos"
    OUTROS = "Outros"


class RfmSortBy(StrEnum):
    """Coluna de ordenação permitida (allow-list; mapeada a coluna física no Gold)."""

    MONETARY_VALUE = "monetary_value"
    RECENCY_DAYS = "recency_days"
    FREQUENCY_BASKETS = "frequency_baskets"


class SortOrder(StrEnum):
    """Direção de ordenação."""

    ASC = "asc"
    DESC = "desc"


class RfmHousehold(BaseModel):
    """Um domicílio na visão detalhada do RFM (grão domicílio, metrics.md §5)."""

    household_id: int = Field(description="Identificador do domicílio (household_id).")
    recency_days: int = Field(
        description="Dias desde a última compra até 2018-01-01 (R; menor = melhor)."
    )
    frequency_baskets: int = Field(
        description="Nº de cestas no período (F; maior = melhor)."
    )
    monetary_value: float = Field(
        description="Receita observada do domicílio na amostra (M; USD)."
    )
    r_score: int = Field(
        description="Score de recência 1–5 (NTILE invertido; 5 = melhor)."
    )
    f_score: int = Field(description="Score de frequência 1–5 (5 = melhor).")
    m_score: int = Field(description="Score de valor monetário 1–5 (5 = melhor).")
    rfm_segment: str = Field(description="Segmento RFM nomeado (ex.: 'Campeões').")


class RfmHouseholdsResponse(BaseModel):
    """RFM por domicílio, paginado — a tabela detalhada da página RFM do frontend."""

    as_of_date: str = Field(description="Data de referência (as-of) do dataset.")
    currency: str = Field(description="Moeda dos valores monetários.")
    total: int = Field(
        description="Nº de domicílios que batem o filtro (para paginação; ignora limit)."
    )
    limit: int = Field(description="Tamanho de página aplicado (<= 200).")
    offset: int = Field(description="Deslocamento aplicado (>= 0).")
    segment: str | None = Field(
        default=None, description="Eco do filtro de segmento (None = todos)."
    )
    households: list[RfmHousehold] = Field(
        description="Página de domicílios, ordenada conforme sort_by/order."
    )
    note: str = Field(default=SAMPLE_NOTE, description="Escopo da receita (amostra).")


# --- Retenção (metrics.md §6) --------------------------------------------------
# Tudo aqui é OBSERVACIONAL: mede a cadência natural da amostra, não o efeito de
# nenhuma ação de CRM. Correlação ≠ causalidade (CLAUDE.md regra 9).

# Ressalva do mês-fronteira parcial para a retenção mensal (metrics.md §6.2).
RETENTION_MONTHLY_NOTE = (
    "Retenção mês-a-mês OBSERVACIONAL (metrics.md §6.2): % de domicílios ativos no "
    "mês M que voltam a comprar em M+1. A ÚLTIMA linha (2017-12 → 2018-01) é "
    "subestimada pelo mês-fronteira parcial: 2018-01 tem só os primeiros dias do "
    "dataset (next_month_partial=true), então a queda NÃO é churn real. "
    "Correlação ≠ causalidade: isto não mede o efeito de nenhuma ação de CRM."
)

# Ressalva de left-censoring para as coortes (metrics.md §6.3).
RETENTION_COHORTS_NOTE = (
    "Coorte de retenção OBSERVACIONAL (metrics.md §6.3). LEFT-CENSORING: "
    "cohort_month = mês da PRIMEIRA aparição do domicílio NA JANELA de dados, NÃO a "
    "aquisição real do cliente. O dataset começa em 2017-01, então a coorte de "
    "janeiro concentra os já-clientes visíveis no início — não são 'novos de "
    "janeiro'. Coortes tardias têm menos meses para maturar (right-censoring): não "
    "compare M12 entre coortes. Correlação ≠ causalidade."
)


class RetentionMonthlyPoint(BaseModel):
    """Um mês da série de retenção período-a-período (grão = mês de atividade)."""

    activity_month: str = Field(
        description="Mês de atividade M (ISO date, 1º dia do mês: YYYY-MM-DD)."
    )
    active_households: int = Field(
        description="Domicílios ativos em M (>= 1 cesta; denominador da taxa)."
    )
    retained_next_month: int = Field(
        description="Domicílios ativos em M que também compraram em M+1 (numerador)."
    )
    retention_rate: float = Field(
        description="retained_next_month / active_households (0..1)."
    )
    next_month_partial: bool = Field(
        description=(
            "True só em 2017-12: M+1 (2018-01) é o mês-fronteira PARCIAL do dataset, "
            "logo a taxa subestima e NÃO é churn real."
        )
    )


class RetentionMonthlyResponse(BaseModel):
    """Série mensal de retenção para o Overview (metrics.md §6.2)."""

    as_of_date: str = Field(description="Data de referência (as-of) do dataset.")
    n_months: int = Field(description="Nº de meses na série (esperado 12).")
    series: list[RetentionMonthlyPoint] = Field(
        description="Pontos ordenados por activity_month (asc)."
    )
    note: str = Field(
        default=RETENTION_MONTHLY_NOTE,
        description="Ressalva do mês-fronteira parcial + aviso observacional.",
    )


class CohortRetentionPoint(BaseModel):
    """Um ponto do triângulo de coorte (mês de atividade dentro de uma coorte)."""

    months_since: int = Field(
        description="Meses decorridos desde o mês da coorte (0 = o próprio mês)."
    )
    activity_month: str = Field(
        description="Mês de atividade medido (ISO date: YYYY-MM-DD)."
    )
    active_households: int = Field(
        description="Domicílios da coorte ativos neste mês de atividade."
    )
    retention_rate: float = Field(
        description="active_households / cohort_size (0..1; é 1.0 em months_since=0)."
    )


class CohortRetention(BaseModel):
    """Uma coorte (domicílios pela primeira aparição na janela) e seu triângulo."""

    cohort_month: str = Field(
        description=(
            "Mês da PRIMEIRA aparição na janela (ISO date). NÃO é aquisição real "
            "(left-censoring — ver note)."
        )
    )
    cohort_size: int = Field(
        description="Nº de domicílios na coorte (constante; base da taxa)."
    )
    points: list[CohortRetentionPoint] = Field(
        description="Triângulo da coorte, ordenado por months_since (asc)."
    )


class RetentionCohortsResponse(BaseModel):
    """Triângulo de coortes de retenção para a página de retenção (metrics.md §6.3)."""

    as_of_date: str = Field(description="Data de referência (as-of) do dataset.")
    n_cohorts: int = Field(description="Nº de coortes distintas (esperado 12).")
    cohorts: list[CohortRetention] = Field(
        description="Coortes ordenadas por cohort_month (asc)."
    )
    note: str = Field(
        default=RETENTION_COHORTS_NOTE,
        description="Ressalva de left/right-censoring + aviso observacional.",
    )
