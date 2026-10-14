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
