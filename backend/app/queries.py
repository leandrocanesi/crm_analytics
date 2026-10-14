"""SQL **predefinido e parametrizado** (o "sql/" da API).

Todas as consultas são constantes fixas aqui — o frontend NUNCA envia SQL
(CLAUDE.md regra 7). Valores dinâmicos (quando houver) entram por placeholders
``?`` ligados em ``SnapshotManager.query``, nunca por concatenação de strings.

Cada query lê SOMENTE tabelas publicadas no snapshot e expõe o que o Gold já
calculou — não recalcula métricas (as definições vivem em ``docs/metrics.md``).
"""

from __future__ import annotations

# Metadados técnicos do snapshot (1 linha). Ver _snapshot_meta em snapshot.py do pipeline.
META = """
SELECT
    built_at,
    gold_source,
    revenue_total,
    basket_count,
    household_count,
    git_commit,
    schema_version,
    content_hash,
    snapshot_version
FROM _snapshot_meta
LIMIT 1
"""

# Cards do Overview — derivados do grão cesta (fct_basket), a fonte única.
# total_revenue reconcilia a âncora (SUM basket_revenue); avg_basket_value é a
# razão receita/cestas (ticket médio POR CESTA, metrics.md §4 — jamais no grão linha).
OVERVIEW = """
SELECT
    SUM(basket_revenue)           AS total_revenue,
    COUNT(*)                      AS n_baskets,
    COUNT(DISTINCT household_id)  AS n_active_households
FROM fct_basket
"""

# Série temporal semanal — lê a tabela já agregada (metrics.md §1), ordenada por week.
WEEKLY_REVENUE = """
SELECT
    week,
    revenue,
    n_baskets,
    n_active_households
FROM agg_weekly_revenue
ORDER BY week
"""

# Distribuição dos 7 segmentos RFM (metrics.md §5.2), por nº de domicílios.
# Soma de n_households deve reconciliar os 2.469 domicílios do universo.
RFM_SEGMENTS = """
SELECT
    rfm_segment          AS segment,
    COUNT(*)             AS n_households,
    SUM(monetary_value)  AS monetary_value
FROM agg_household_rfm
GROUP BY rfm_segment
ORDER BY n_households DESC
"""

# RFM por domicílio (grão domicílio, metrics.md §5) — a "tabela detalhada" do RFM.
#
# Segurança (CLAUDE.md regra 7): o SQL é FIXO aqui. Os únicos valores dinâmicos são
# ligados por placeholders ``?`` (bind): o filtro de segmento, o LIMIT e o OFFSET.
# A ordenação NÃO pode ser parametrizada por bind (SQL não liga identificadores),
# então ``{order_by}`` e ``{order}`` são preenchidos via ``str.format`` APENAS a
# partir dos mapas allow-list abaixo — nunca com string crua do cliente.
# Desempate por ``household_id`` garante paginação estável (ordem total determinística).
RFM_HOUSEHOLDS = """
SELECT
    household_id,
    recency_days,
    frequency_baskets,
    monetary_value,
    r_score,
    f_score,
    m_score,
    rfm_segment
FROM agg_household_rfm
WHERE (? IS NULL OR rfm_segment = ?)
ORDER BY {order_by} {order}, household_id ASC
LIMIT ? OFFSET ?
"""

# COUNT com o MESMO filtro — alimenta ``total`` (nº de domicílios que batem o
# filtro) para a paginação do frontend.
RFM_HOUSEHOLDS_COUNT = """
SELECT COUNT(*) AS total
FROM agg_household_rfm
WHERE (? IS NULL OR rfm_segment = ?)
"""

# Allow-list de colunas ordenáveis: nome exposto na API -> coluna física no Gold.
# Apenas estes valores podem entrar no ORDER BY (defesa contra SQL injection).
RFM_SORT_COLUMNS: dict[str, str] = {
    "monetary_value": "monetary_value",
    "recency_days": "recency_days",
    "frequency_baskets": "frequency_baskets",
}

# Allow-list de direções de ordenação.
RFM_SORT_ORDERS: dict[str, str] = {"asc": "ASC", "desc": "DESC"}
