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

# Retenção período-a-período (mensal, metrics.md §6.2) — lê a tabela já agregada.
# Grão = mês de atividade (12 linhas). A última linha (2017-12) tem
# next_month_partial = TRUE: 2018-01 é o mês-fronteira parcial do dataset, logo a
# taxa subestima a retenção e NÃO representa churn real. Ordenado por mês ASC.
RETENTION_MONTHLY = """
SELECT
    activity_month,
    active_households,
    retained_next_month,
    retention_rate,
    next_month_partial
FROM agg_retention_monthly
ORDER BY activity_month ASC
"""

# Coorte de retenção (metrics.md §6.3) — triângulo coorte × mês (84 linhas).
# Grão = coorte (mês da PRIMEIRA aparição na janela) × mês de atividade. O service
# monta a estrutura aninhada a partir destas linhas. Ordenado por coorte ASC e,
# dentro da coorte, por meses-desde-a-coorte ASC (estável para o triângulo).
# LEFT-CENSORING: cohort_month = primeira aparição na janela, NÃO a aquisição real.
COHORT_RETENTION = """
SELECT
    cohort_month,
    activity_month,
    months_since,
    cohort_size,
    active_households,
    retention_rate
FROM agg_cohort_retention
ORDER BY cohort_month ASC, months_since ASC
"""

# --- Campanha e Cupom (metrics.md §8, factual 8.1–8.4) -------------------------
# SELECTs FIXOS, sem parâmetros do cliente (CLAUDE.md regra 7). Leem só tabelas
# publicadas. NENHUMA coluna monetária é consultada: os dados não ligam receita a
# campanha (metrics.md §8.0 verdade 3), então não há métrica em $ aqui.

# §8.1 alcance + §8.2.a taxa de resposta por campanha. Datas vêm de dim_campaign
# (agg_campaign_performance não as traz). Ordenado por households_exposed DESC
# (desempate por campaign_id para ordem determinística/estável).
CAMPAIGN_PERFORMANCE = """
SELECT
    p.campaign_id,
    p.campaign_type,
    d.start_date,
    d.end_date,
    p.households_exposed,
    p.households_redeemed,
    p.redemption_rate
FROM agg_campaign_performance AS p
JOIN dim_campaign AS d USING (campaign_id)
ORDER BY p.households_exposed DESC, p.campaign_id ASC
"""

# Universo alcançado (DISTINCT) — NÃO é a soma dos households_exposed por campanha
# (metrics.md §8.0.2: alcance não é aditivo). Alimenta households_exposed_total.
CAMPAIGN_EXPOSED_TOTAL = """
SELECT COUNT(DISTINCT household_id) AS households_exposed_total
FROM bridge_household_campaign
"""

# §8.4 resgate por tipo A/B/C. n_campaigns por tipo vem de dim_campaign (contagem
# de campanhas); as demais métricas, de agg_coupon_redemption (grão tipo).
# Ordenado por campaign_type ASC. Expostos/resgatadores NÃO são aditivos entre tipos
# (um lar pode estar em >1 tipo); só n_redemption_events soma (= 2.102).
CAMPAIGN_BY_TYPE = """
SELECT
    r.campaign_type,
    c.n_campaigns,
    r.households_exposed,
    r.n_redemption_events,
    r.households_redeemed,
    r.n_coupons_redeemed,
    r.redemption_rate
FROM agg_coupon_redemption AS r
JOIN (
    SELECT campaign_type, COUNT(*) AS n_campaigns
    FROM dim_campaign
    GROUP BY campaign_type
) AS c USING (campaign_type)
ORDER BY r.campaign_type ASC
"""

# §8.3 sobreposição — resumo (total distinto, média, máximo). Base para a cobertura.
CAMPAIGN_OVERLAP_SUMMARY = """
SELECT
    COUNT(*)                     AS total_exposed,
    AVG(n_campaigns_exposed)     AS avg_campaigns_per_household,
    MAX(n_campaigns_exposed)     AS max_campaigns_per_household
FROM agg_household_campaign_exposure
"""

# §8.3 histograma: quantos domicílios receberam N campanhas. Soma = total_exposed.
CAMPAIGN_OVERLAP_DISTRIBUTION = """
SELECT
    n_campaigns_exposed,
    COUNT(*) AS n_households
FROM agg_household_campaign_exposure
GROUP BY n_campaigns_exposed
ORDER BY n_campaigns_exposed ASC
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
