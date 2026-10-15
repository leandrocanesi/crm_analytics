"""Configuração estática da camada Gold.

Cada tabela/visão analítica Gold é descrita por um :class:`GoldSpec`, que carrega:
  - as dependências **explícitas** de montante — tabelas Silver (``silver_deps``)
    e/ou tabelas Gold já materializadas (``gold_deps``) — que viram dependências
    do asset Dagster (silver → gold, gold → gold) e fontes nomeadas no SQL;
  - o SQL de transformação (``transform_sql``), escrito em DuckDB sobre o Parquet
    de montante, com placeholders ``{silver_<tabela>}`` / ``{gold_<tabela>}``;
  - o grão **explícito** (``grain`` descritivo + ``grain_columns`` para o check de
    unicidade) e a contagem de linhas esperada (``expected_rows``);
  - os asset checks declarativos: reconciliações de valor (:class:`ReconcileCheck`,
    tipicamente contra a âncora de receita US$ 4.596.039,58) e checks de violação
    (:class:`ViolationCheck`, ex. limites de recência, ativos ≤ universo).

Princípios (CLAUDE.md regras 4, 5, 6 e docs/data-model.md §3–§5):
  - **Fonte única da receita:** só a fato (``silver.transactions``) ou um agregado
    já derivado dela (``gold.fct_basket``) — nunca um join que faça fan-out.
  - **Idempotência:** todo SQL é determinístico; os ``NTILE`` do RFM usam
    ``household_id`` como desempate para que o mesmo input produza o mesmo output.
  - **Data de referência FIXA** (``AS_OF_DATE`` = 2018-01-01) para recência; nunca
    a data atual do computador.

Os números esperados foram conferidos por prototipagem real sobre o Parquet
Silver em 2026-10-14 (ver docs/metrics.md §7 e as âncoras em §0).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import (
    AS_OF_DATE,
    BASKET_ANCHOR,
    CAMPAIGN_COUNT,
    CAMPAIGN_EXPOSURE_ANCHOR,
    COUPONS_REDEEMED_ANCHOR,
    DATA_WINDOW_END,
    DATA_WINDOW_START,
    EXPOSED_HOUSEHOLDS_ANCHOR,
    HOUSEHOLD_UNIVERSE,
    LINE_ANCHOR,
    REDEEMER_HOUSEHOLDS_ANCHOR,
    REDEEMER_PAIRS_ANCHOR,
    REDEMPTION_EVENT_ANCHOR,
    REVENUE_ANCHOR_TOL_USD,
    REVENUE_ANCHOR_USD,
)

# ---------------------------------------------------------------------------
# Descritores de asset check reutilizados pela fábrica de assets Gold.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconcileCheck:
    """Reconciliação de um escalar agregado contra um valor esperado.

    O check executa ``SELECT <value_expr> FROM <gold>`` e passa (ERROR) se o
    observado ficar dentro de ``tol`` do ``expected``. Usado sobretudo para
    provar que cada visão Gold que expõe receita reproduz **exatamente** a âncora
    US$ 4.596.039,58 (qualquer desvio = fan-out ou filtro indevido; data-model §4).
    """

    name: str
    description: str
    value_expr: str
    expected: float
    tol: float = REVENUE_ANCHOR_TOL_USD


@dataclass(frozen=True)
class ViolationCheck:
    """Conta linhas que violam uma condição; passa (ERROR) se a contagem for 0.

    ``where_expr`` é uma condição SQL que descreve o estado **inválido** (ex.
    ``recency_days < 0 OR recency_days > 365``). Mantém os checks legíveis: o que
    está escrito é exatamente o que não pode acontecer.
    """

    name: str
    description: str
    where_expr: str


@dataclass(frozen=True)
class IntegrityCheck:
    """Check de integridade **cross-table**: roda um SQL que retorna um único
    inteiro (o nº de violações) e passa (ERROR) se esse inteiro for 0.

    Diferente de :class:`ReconcileCheck`/:class:`ViolationCheck` (que só enxergam a
    própria tabela Gold), ``count_sql`` pode cruzar a tabela recém-gravada com as
    suas fontes de montante. Usa os MESMOS placeholders que ``transform_sql``:
      - ``{this}``            — a própria tabela Gold (o Parquet já persistido);
      - ``{gold_<t>}`` / ``{silver_<t>}`` — as fontes declaradas em ``*_deps``.
    Serve para provar, p.ex., que ``active_households`` de cada mês da retenção
    bate com o COUNT(DISTINCT household) ativo na base de atividade.
    """

    name: str
    description: str
    count_sql: str


@dataclass(frozen=True)
class GoldSpec:
    """Especificação de uma tabela Gold (transformação + validações)."""

    name: str
    transform_sql: str
    grain: str
    grain_columns: tuple[str, ...]
    expected_rows: int
    silver_deps: tuple[str, ...] = field(default_factory=tuple)
    gold_deps: tuple[str, ...] = field(default_factory=tuple)
    reconcile_checks: tuple[ReconcileCheck, ...] = field(default_factory=tuple)
    violation_checks: tuple[ViolationCheck, ...] = field(default_factory=tuple)
    integrity_checks: tuple[IntegrityCheck, ...] = field(default_factory=tuple)
    description: str = ""

    @property
    def all_deps(self) -> tuple[tuple[str, str], ...]:
        """Dependências como pares (camada, tabela), sem duplicatas, ordem estável."""
        pairs = [("silver", t) for t in self.silver_deps]
        pairs += [("gold", t) for t in self.gold_deps]
        return tuple(pairs)


# ---------------------------------------------------------------------------
# SQL de transformação por tabela. Placeholders {silver_<t>} / {gold_<t>} são
# resolvidos em gold.py para expressões read_parquet sobre o Parquet de montante.
# ---------------------------------------------------------------------------

# 1) fct_basket — grão 1 CESTA (pedra fundamental, metrics.md §3/§7).
#    basket_id mapeia 1:1 para household/store/timestamp/week (verificado na
#    inspeção), logo ANY_VALUE é determinístico (todos os valores do grupo são
#    idênticos). n_items = COUNT(*) de linhas (decisão 3, NÃO SUM(quantity), que
#    misturaria unidades e peso). basket_revenue = SUM(sales_value) SEM filtro
#    (decisão 1 — preserva a âncora de receita).
_SQL_FCT_BASKET = """
SELECT
    basket_id,
    ANY_VALUE(household_id)          AS household_id,
    ANY_VALUE(store_id)              AS store_id,
    ANY_VALUE(transaction_timestamp) AS transaction_timestamp,
    ANY_VALUE(week)                  AS week,
    COUNT(*)                         AS n_items,        -- nº de linhas/produtos na cesta
    SUM(sales_value)                 AS basket_revenue  -- receita observada da cesta
FROM {silver_transactions}
GROUP BY basket_id
"""

# 2) agg_weekly_revenue — grão SEMANA (metrics.md §1/§2/§4). Derivado de
#    fct_basket (barato e já reconciliado). n_active_households = domicílios com
#    >= 1 cesta na semana (decisão 2); NÃO é aditivo entre semanas.
_SQL_AGG_WEEKLY_REVENUE = """
SELECT
    week,
    SUM(basket_revenue)          AS revenue,
    COUNT(DISTINCT basket_id)    AS n_baskets,
    COUNT(DISTINCT household_id) AS n_active_households
FROM {gold_fct_basket}
GROUP BY week
ORDER BY week
"""

# 3) agg_household_rfm — grão 1 DOMICÍLIO (base de CRM, metrics.md §5).
#    R = dias desde a última compra vs. data-âncora FIXA 2018-01-01 (R invertido
#    no score: recência menor => 5). F = nº de cestas. M = receita do domicílio.
#    Scores por quintil NTILE(5); household_id é o desempate que torna os quintis
#    DETERMINÍSTICOS (idempotência) apesar dos empates mencionados em §5.2.
#    rfm_segment aplica a tabela APROVADA (§5.2) NA ORDEM — a 1ª regra satisfeita
#    vence; o resto cai em 'Outros'.
_SQL_AGG_HOUSEHOLD_RFM = f"""
WITH base AS (
    SELECT
        household_id,
        DATEDIFF('day', MAX(transaction_timestamp)::date, DATE '{AS_OF_DATE}')
            AS recency_days,
        COUNT(DISTINCT basket_id) AS frequency_baskets,
        SUM(basket_revenue)       AS monetary_value
    FROM {{gold_fct_basket}}
    GROUP BY household_id
),
scored AS (
    SELECT
        *,
        -- R invertido: ORDER BY recency DESC => recência maior (pior) = tile 1,
        -- recência menor (melhor) = tile 5.
        NTILE(5) OVER (ORDER BY recency_days DESC, household_id)     AS r_score,
        NTILE(5) OVER (ORDER BY frequency_baskets ASC, household_id) AS f_score,
        NTILE(5) OVER (ORDER BY monetary_value ASC, household_id)    AS m_score
    FROM base
)
SELECT
    household_id,
    recency_days,
    frequency_baskets,
    monetary_value,
    r_score,
    f_score,
    m_score,
    CASE
        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Campeões'
        WHEN f_score >= 4 AND m_score >= 3                  THEN 'Leais'
        WHEN r_score >= 4 AND f_score BETWEEN 2 AND 3       THEN 'Potenciais'
        WHEN r_score = 5 AND f_score <= 2                   THEN 'Novos'
        WHEN r_score <= 2 AND f_score >= 3 AND m_score >= 3 THEN 'Em risco'
        WHEN r_score <= 2 AND f_score <= 2                  THEN 'Hibernando / Perdidos'
        ELSE 'Outros'
    END AS rfm_segment
FROM scored
"""

# 4) agg_household_activity_month — grão DOMICÍLIO × MÊS ATIVO (base de retenção
#    período-a-período, decisão 5 / metrics.md §6.2). Presença da linha = ativo no
#    mês (>= 1 cesta). A matriz de retenção P→P+1 é DERIVÁVEL desta base (não é
#    materializada agora). Cada cesta cai em exatamente um mês => a receita
#    mensal particiona a âncora. Há um mês-fronteira parcial 2018-01 (semana 53).
_SQL_AGG_HOUSEHOLD_ACTIVITY_MONTH = """
SELECT
    household_id,
    date_trunc('month', transaction_timestamp)::date AS activity_month,
    COUNT(DISTINCT basket_id) AS n_baskets,
    SUM(basket_revenue)       AS monthly_revenue
FROM {gold_fct_basket}
GROUP BY household_id, date_trunc('month', transaction_timestamp)::date
ORDER BY household_id, activity_month
"""

# 5) agg_retention_monthly — grão MÊS M de ORIGEM (retenção período-a-período,
#    PRIMÁRIA, metrics.md §6.2). Para cada mês M: ativos em M (denominador) e
#    quantos desses também compraram em M+1 (numerador). "Ativo" = >= 1 cesta no
#    mês (consistente com §2). A base já está no grão domicílio × mês ativo, logo
#    um LEFT JOIN da base contra ela mesma deslocada de 1 mês dá a retenção; o
#    COUNT(DISTINCT n.household_id) só conta quem reaparece em M+1 (idempotente).
#    DECISÃO de fronteira: M = 2018-01 é OMITIDO como origem — seu M+1 (2018-02)
#    não é observável, então a taxa seria espúria. Mantemos 12 linhas de origem
#    (2017-01 .. 2017-12). A última (2017-12 -> 2018-01) usa o mês-fronteira
#    PARCIAL 2018-01 como M+1 e é marcada com next_month_partial = TRUE para a UI
#    sinalizar que a taxa está subestimada (não é churn real, é fim da janela).
_SQL_AGG_RETENTION_MONTHLY = """
WITH monthly AS (
    -- grão já é domicílio × mês ativo; DISTINCT é defensivo (não altera o grão).
    SELECT DISTINCT household_id, activity_month
    FROM {gold_agg_household_activity_month}
),
origin AS (
    SELECT
        m.activity_month,
        COUNT(DISTINCT m.household_id) AS active_households,     -- denominador (ativos em M)
        COUNT(DISTINCT n.household_id) AS retained_next_month    -- numerador (ativos em M e M+1)
    FROM monthly m
    LEFT JOIN monthly n
        ON  n.household_id   = m.household_id
        AND n.activity_month = m.activity_month + INTERVAL 1 MONTH
    -- M+1 precisa ser observável: 2018-01 como origem teria M+1 = 2018-02 (vazio).
    WHERE m.activity_month < DATE '2018-01-01'
    GROUP BY m.activity_month
)
SELECT
    activity_month,
    active_households,
    retained_next_month,
    retained_next_month::DOUBLE / active_households AS retention_rate,
    (activity_month + INTERVAL 1 MONTH) = DATE '2018-01-01' AS next_month_partial
FROM origin
ORDER BY activity_month
"""

# 6) agg_cohort_retention — grão COORTE × MÊS-DE-ATIVIDADE (retenção por coorte,
#    SECUNDÁRIA/DIDÁTICA, metrics.md §6.3). coorte = mês da PRIMEIRA cesta
#    OBSERVADA do domicílio dentro da janela.
#    *** LEFT-CENSORING (armadilha central, §6.3): cohort_month é "primeira
#    aparição na janela", NÃO a aquisição real do cliente. Como os dados começam
#    em 2017-01, a maioria dos domicílios cai na coorte de janeiro só porque é
#    onde a janela abre — não porque foram adquiridos ali. NÃO ler a coorte de
#    janeiro como "novos de janeiro". ***
#    Cada domicílio pertence a EXATAMENTE UMA coorte (MIN(activity_month) por
#    household => partição do universo). months_since = 0 é o próprio mês da coorte
#    e, por definição, tem retenção = 1,0. O mês-fronteira 2018-01 (parcial)
#    aparece como o último months_since de cada coorte com taxa subestimada.
_SQL_AGG_COHORT_RETENTION = """
WITH monthly AS (
    SELECT DISTINCT household_id, activity_month
    FROM {gold_agg_household_activity_month}
),
first_seen AS (
    -- coorte do domicílio = mês da sua primeira aparição na janela (left-censored).
    SELECT household_id, MIN(activity_month) AS cohort_month
    FROM monthly
    GROUP BY household_id
),
cohort_sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size
    FROM first_seen
    GROUP BY cohort_month
),
activity AS (
    SELECT
        f.cohort_month,
        m.activity_month,
        COUNT(DISTINCT m.household_id) AS active_households
    FROM monthly m
    JOIN first_seen f USING (household_id)
    GROUP BY f.cohort_month, m.activity_month
)
SELECT
    a.cohort_month,
    a.activity_month,
    DATEDIFF('month', a.cohort_month, a.activity_month) AS months_since,
    c.cohort_size,
    a.active_households,
    a.active_households::DOUBLE / c.cohort_size AS retention_rate
FROM activity a
JOIN cohort_sizes c USING (cohort_month)
ORDER BY a.cohort_month, a.activity_month
"""


# ===========================================================================
# CAMPANHA / CUPOM (Marketing Analytics) — metrics.md §8, escopo v1 = SÓ o
# factual 8.1–8.4. *** REGRA ANTI-FAN-OUT (§8.0.2): NENHUMA destas tabelas toca
# em sales_value — exposição e resgate são EVENTOS/DISTRIBUIÇÃO, nunca receita.
# Receita influenciada (§8.5) e pré/pós (§8.6) foram EXCLUÍDAS da v1. ***
# campaign_type preserva o valor REAL da origem ('Type A'/'Type B'/'Type C');
# não se inventa um código 'A/B/C' (CLAUDE.md regra 1 / data-dictionary §7).
# ===========================================================================

# 7) bridge_household_campaign — grão 1 DOMICÍLIO × CAMPANHA (§8.3). Ponte N:N
#    limpa, promovida da Silver `campaigns` (quem foi ALVO de cada campanha —
#    distribuição, NÃO engajamento §8.0 verdade 1). Base do não-fan-out: alcance
#    e taxas derivam DELA, nunca de um join com transactions. 6.589 pares
#    distintos (0 duplicatas), 1.559 domicílios distintos.
_SQL_BRIDGE_HOUSEHOLD_CAMPAIGN = """
SELECT
    campaign_id,
    household_id
FROM {silver_campaigns}
"""

# 8) dim_campaign — grão 1 CAMPANHA (§8.1/8.4). As 27 campanhas com tipo e janela
#    (de campaign_descriptions) + households_exposed = alcance (§8.1). LEFT JOIN a
#    partir das descrições => a dimensão tem SEMPRE as 27 campanhas, mesmo que
#    alguma viesse a ter 0 exposição (hoje todas as 27 têm >= 1). households_exposed
#    = COUNT(DISTINCT household) na ponte; como os pares são distintos, a SOMA de
#    households_exposed pelas campanhas == 6.589 (as linhas da ponte). ATENÇÃO: o
#    alcance NÃO é aditivo num "universo" — o universo alcançado é 1.559 DISTINTOS,
#    não a soma 6.589 (§8.0.2).
_SQL_DIM_CAMPAIGN = """
SELECT
    d.campaign_id,
    d.campaign_type,                              -- 'Type A' | 'Type B' | 'Type C' (valor real)
    d.start_date,
    d.end_date,
    COUNT(DISTINCT b.household_id) AS households_exposed  -- alcance (§8.1)
FROM {silver_campaign_descriptions} d
LEFT JOIN {gold_bridge_household_campaign} b USING (campaign_id)
GROUP BY d.campaign_id, d.campaign_type, d.start_date, d.end_date
"""

# 9) agg_household_campaign_exposure — grão 1 DOMICÍLIO EXPOSTO (§8.3). Atributo
#    n_campaigns_exposed = nº de campanhas que cada lar recebeu (sobreposição;
#    média 4,23, máx. 15). Habilita cruzar exposição × segmento RFM depois
#    (DESCRITIVO — "a quem o marketing falou", NÃO teste de efeito; viés de
#    seleção de público §8.3). Cobre só os 1.559 EXPOSTOS; um cruzamento futuro com
#    os 2.469 trata ausência como 0. SUM(n_campaigns_exposed) == 6.589.
_SQL_AGG_HOUSEHOLD_CAMPAIGN_EXPOSURE = """
SELECT
    household_id,
    COUNT(DISTINCT campaign_id) AS n_campaigns_exposed
FROM {gold_bridge_household_campaign}
GROUP BY household_id
"""

# 10) fct_coupon_redemption — grão 1 EVENTO DE RESGATE (§8.4). Fato de evento
#     (2.102 linhas), colunas reais de coupon_redemptions + campaign_type por join
#     (contexto). *** NÃO é multiplicador de receita: a tabela não tem campo
#     monetário e NÃO se liga a uma linha de venda (§8.0 verdade 3). *** Resgate é
#     evento observado, NÃO conversão causada (§8.0 verdade 2). LEFT JOIN preserva
#     os 2.102 eventos mesmo se o FK falhar (verificado: 0 falham).
_SQL_FCT_COUPON_REDEMPTION = """
SELECT
    r.household_id,
    r.coupon_upc,
    r.campaign_id,
    r.redemption_date,
    d.campaign_type        -- 'Type A/B/C' via join (contexto p/ agregar por tipo)
FROM {silver_coupon_redemptions} r
LEFT JOIN {silver_campaign_descriptions} d USING (campaign_id)
"""

# 11) agg_campaign_performance — grão 1 CAMPANHA (§8.1/8.2). Alcance + taxa de
#     resposta HOUSEHOLD-LEVEL. households_redeemed = domicílios DISTINTOS que
#     resgataram >= 1 cupom ligado à campanha; redemption_rate = redeemed /
#     EXPOSTOS (§8.2.a — denominador é EXPOSTOS, jamais "cupons enviados").
#     *** A taxa é binária por domicílio (resgatou sim/não); o EVENTO nunca é
#     numerador de taxa — dividir 2.102 eventos por domicílios daria "135%",
#     o erro júnior clássico (§8.2). *** LEFT JOIN => as 27 campanhas aparecem;
#     campanha sem resgate (ex.: campanha 24) fica com redeemed=0, rate=0,0.
_SQL_AGG_CAMPAIGN_PERFORMANCE = """
WITH redeemed AS (
    SELECT
        campaign_id,
        COUNT(DISTINCT household_id) AS households_redeemed
    FROM {gold_fct_coupon_redemption}
    GROUP BY campaign_id
)
SELECT
    c.campaign_id,
    c.campaign_type,
    c.households_exposed,
    COALESCE(r.households_redeemed, 0) AS households_redeemed,
    -- taxa de resposta household-level: resgatadores DISTINTOS / expostos (∈[0,1]).
    COALESCE(r.households_redeemed, 0)::DOUBLE / c.households_exposed AS redemption_rate
FROM {gold_dim_campaign} c
LEFT JOIN redeemed r USING (campaign_id)
ORDER BY CAST(c.campaign_id AS INTEGER)
"""

# 12) agg_coupon_redemption — grão 1 TIPO DE CAMPANHA (A/B/C) (§8.4). Volume e
#     alcance de resgate por tipo, NORMALIZADO por expostos. *** Reportar a taxa
#     (resgate/expostos), não só o volume: "Tipo X teve mais resgates" pode só
#     refletir que foi enviado a mais gente. *** n_redemption_events é ADITIVO
#     (cada evento tem exatamente 1 campanha => 1 tipo) e soma 2.102; já
#     households_exposed / households_redeemed / n_coupons_redeemed NÃO são aditivos
#     entre tipos (um lar/cupom pode cair em >1 tipo) — por isso cada um é DISTINCT
#     dentro do tipo e a soma entre tipos excede os totais globais (esperado).
_SQL_AGG_COUPON_REDEMPTION = """
WITH exposed AS (
    SELECT
        c.campaign_type,
        COUNT(DISTINCT b.household_id) AS households_exposed   -- distinto DENTRO do tipo
    FROM {gold_bridge_household_campaign} b
    JOIN {gold_dim_campaign} c USING (campaign_id)
    GROUP BY c.campaign_type
),
redeemed AS (
    SELECT
        campaign_type,
        COUNT(*)                     AS n_redemption_events,   -- volume (aditivo => 2.102)
        COUNT(DISTINCT household_id) AS households_redeemed,   -- distinto DENTRO do tipo
        COUNT(DISTINCT coupon_upc)   AS n_coupons_redeemed     -- distinto DENTRO do tipo
    FROM {gold_fct_coupon_redemption}
    GROUP BY campaign_type
)
SELECT
    e.campaign_type,
    e.households_exposed,
    COALESCE(r.n_redemption_events, 0) AS n_redemption_events,
    COALESCE(r.households_redeemed, 0)  AS households_redeemed,
    COALESCE(r.n_coupons_redeemed, 0)   AS n_coupons_redeemed,
    COALESCE(r.households_redeemed, 0)::DOUBLE / e.households_exposed AS redemption_rate
FROM exposed e
LEFT JOIN redeemed r USING (campaign_type)
ORDER BY e.campaign_type
"""


# ---------------------------------------------------------------------------
# Especificações das tabelas Gold (ordem de implementação = metrics.md §7).
# ---------------------------------------------------------------------------

GOLD_SPECS: tuple[GoldSpec, ...] = (
    GoldSpec(
        name="fct_basket",
        transform_sql=_SQL_FCT_BASKET,
        grain="1 cesta (basket_id)",
        grain_columns=("basket_id",),
        expected_rows=BASKET_ANCHOR,
        silver_deps=("transactions",),
        description=(
            "Fato de cesta: 1 linha por basket_id com household/store/timestamp, "
            "n_items (nº de linhas) e basket_revenue (SUM sales_value, sem filtro)."
        ),
        reconcile_checks=(
            ReconcileCheck(
                name="basket_revenue_reconciles",
                description="SUM(basket_revenue) == âncora US$ 4.596.039,58 (sem fan-out).",
                value_expr="SUM(basket_revenue)",
                expected=REVENUE_ANCHOR_USD,
            ),
            ReconcileCheck(
                name="basket_count_matches",
                description="COUNT(DISTINCT basket_id) == 155.848 cestas.",
                value_expr="COUNT(DISTINCT basket_id)",
                expected=float(BASKET_ANCHOR),
                tol=0.0,
            ),
            ReconcileCheck(
                name="item_count_matches",
                description="SUM(n_items) == 1.469.307 linhas item-de-linha.",
                value_expr="SUM(n_items)",
                expected=float(LINE_ANCHOR),
                tol=0.0,
            ),
        ),
        violation_checks=(
            ViolationCheck(
                name="basket_revenue_non_negative",
                description="Nenhuma cesta com receita negativa.",
                where_expr="basket_revenue < 0",
            ),
            ViolationCheck(
                name="n_items_positive",
                description="Toda cesta tem pelo menos 1 linha.",
                where_expr="n_items < 1",
            ),
        ),
    ),
    GoldSpec(
        name="agg_weekly_revenue",
        transform_sql=_SQL_AGG_WEEKLY_REVENUE,
        grain="1 semana (week)",
        grain_columns=("week",),
        expected_rows=53,
        gold_deps=("fct_basket",),
        description=(
            "Série semanal: revenue, n_baskets e n_active_households (ativo = >= 1 "
            "cesta na semana). Derivada de fct_basket; alimenta os cards do Overview."
        ),
        reconcile_checks=(
            ReconcileCheck(
                name="revenue_reconciles",
                description="SUM(revenue) sobre as 53 semanas == US$ 4.596.039,58.",
                value_expr="SUM(revenue)",
                expected=REVENUE_ANCHOR_USD,
            ),
            ReconcileCheck(
                name="basket_count_reconciles",
                description="SUM(n_baskets) == 155.848 (cross-check com fct_basket).",
                value_expr="SUM(n_baskets)",
                expected=float(BASKET_ANCHOR),
                tol=0.0,
            ),
        ),
        violation_checks=(
            ViolationCheck(
                name="active_hh_within_universe",
                description="Ativos por semana <= 2.469 (universo de domicílios).",
                where_expr=f"n_active_households > {HOUSEHOLD_UNIVERSE}",
            ),
        ),
    ),
    GoldSpec(
        name="agg_household_rfm",
        transform_sql=_SQL_AGG_HOUSEHOLD_RFM,
        grain="1 domicílio (household_id)",
        grain_columns=("household_id",),
        expected_rows=HOUSEHOLD_UNIVERSE,
        gold_deps=("fct_basket",),
        description=(
            "RFM por domicílio: recency_days (as-of 2018-01-01), frequency_baskets, "
            "monetary_value, scores NTILE(5) (R invertido) e rfm_segment (§5.2)."
        ),
        reconcile_checks=(
            ReconcileCheck(
                name="rfm_monetary_reconciles",
                description="SUM(monetary_value) == US$ 4.596.039,58 (M particiona a receita).",
                value_expr="SUM(monetary_value)",
                expected=REVENUE_ANCHOR_USD,
            ),
            ReconcileCheck(
                name="rfm_frequency_reconciles",
                description="SUM(frequency_baskets) == 155.848 cestas.",
                value_expr="SUM(frequency_baskets)",
                expected=float(BASKET_ANCHOR),
                tol=0.0,
            ),
        ),
        violation_checks=(
            ViolationCheck(
                name="rfm_recency_bounds",
                description="recency_days em [0, 365] (negativo = data de referência errada).",
                where_expr="recency_days < 0 OR recency_days > 365",
            ),
            ViolationCheck(
                name="rfm_scores_in_range",
                description="r_score, f_score e m_score em [1, 5].",
                where_expr=(
                    "r_score NOT BETWEEN 1 AND 5 "
                    "OR f_score NOT BETWEEN 1 AND 5 "
                    "OR m_score NOT BETWEEN 1 AND 5"
                ),
            ),
            ViolationCheck(
                name="rfm_segment_not_null",
                description="Todo domicílio recebe um rótulo de segmento (inclui 'Outros').",
                where_expr="rfm_segment IS NULL",
            ),
        ),
    ),
    GoldSpec(
        name="agg_household_activity_month",
        transform_sql=_SQL_AGG_HOUSEHOLD_ACTIVITY_MONTH,
        grain="1 domicílio × mês ativo (household_id, activity_month)",
        grain_columns=("household_id", "activity_month"),
        expected_rows=24_449,
        gold_deps=("fct_basket",),
        description=(
            "Base de atividade mensal (domicílio × mês com >= 1 cesta) para a "
            "retenção período-a-período (decisão 5). A matriz P→P+1 é derivável "
            "desta base; não é materializada agora."
        ),
        reconcile_checks=(
            ReconcileCheck(
                name="activity_revenue_reconciles",
                description="SUM(monthly_revenue) == US$ 4.596.039,58 (mês particiona a receita).",
                value_expr="SUM(monthly_revenue)",
                expected=REVENUE_ANCHOR_USD,
            ),
            ReconcileCheck(
                name="activity_basket_reconciles",
                description="SUM(n_baskets) == 155.848 (cada cesta em exatamente um mês).",
                value_expr="SUM(n_baskets)",
                expected=float(BASKET_ANCHOR),
                tol=0.0,
            ),
        ),
        violation_checks=(
            # Janela observada: 2017-01 .. 2018-01. O mês-fronteira 2018-01 é
            # parcial (fim da semana 53) e é esperado — por isso o teto é o
            # primeiro dia de 2018-01 (DATA_WINDOW_END), não 2017-12.
            ViolationCheck(
                name="activity_month_within_window",
                description=(
                    "activity_month dentro da janela observada "
                    f"[{DATA_WINDOW_START}, {DATA_WINDOW_END}]."
                ),
                where_expr=(
                    f"activity_month < DATE '{DATA_WINDOW_START}' "
                    f"OR activity_month > DATE '{DATA_WINDOW_END}'"
                ),
            ),
            ViolationCheck(
                name="activity_counts_positive",
                description="Todo par domicílio×mês ativo tem >= 1 cesta.",
                where_expr="n_baskets < 1",
            ),
        ),
    ),
    GoldSpec(
        name="agg_retention_monthly",
        transform_sql=_SQL_AGG_RETENTION_MONTHLY,
        grain="1 mês de origem M (activity_month)",
        grain_columns=("activity_month",),
        # 13 meses observados [2017-01 .. 2018-01]; 2018-01 é omitido como origem
        # (M+1 não observável) => 12 linhas de origem (2017-01 .. 2017-12).
        expected_rows=12,
        gold_deps=("agg_household_activity_month",),
        description=(
            "Retenção período-a-período mensal (PRIMÁRIA, metrics.md §6.2): por mês "
            "M, active_households (ativos em M), retained_next_month (ativos em M e "
            "M+1) e retention_rate = num/denom. 'Ativo' = >= 1 cesta no mês. M = "
            "2018-01 é omitido como origem (M+1 não observável); a linha 2017-12 usa "
            "o mês parcial 2018-01 como M+1 e é marcada com next_month_partial=TRUE "
            "(taxa subestimada pelo fim da janela, não churn real). Observacional: "
            "retenção != efeito de CRM (correlação != causalidade)."
        ),
        violation_checks=(
            ViolationCheck(
                name="retention_rate_in_unit_interval",
                description="Toda retention_rate em [0, 1].",
                where_expr="retention_rate < 0 OR retention_rate > 1",
            ),
            ViolationCheck(
                name="retained_le_active",
                description="retained_next_month <= active_households em toda linha.",
                where_expr="retained_next_month > active_households",
            ),
            ViolationCheck(
                name="active_households_positive",
                description="Todo mês de origem tem >= 1 domicílio ativo.",
                where_expr="active_households < 1",
            ),
        ),
        integrity_checks=(
            IntegrityCheck(
                name="active_households_matches_base",
                description=(
                    "active_households de cada mês bate com COUNT(DISTINCT household) "
                    "ativo naquele mês em agg_household_activity_month."
                ),
                # Conta meses cujo denominador diverge da base de atividade (deve ser 0).
                count_sql="""
                    SELECT COUNT(*) FROM {this} r
                    WHERE r.active_households <> (
                        SELECT COUNT(DISTINCT a.household_id)
                        FROM {gold_agg_household_activity_month} a
                        WHERE a.activity_month = r.activity_month
                    )
                """,
            ),
        ),
    ),
    GoldSpec(
        name="agg_cohort_retention",
        transform_sql=_SQL_AGG_COHORT_RETENTION,
        grain="1 coorte × mês de atividade (cohort_month, activity_month)",
        grain_columns=("cohort_month", "activity_month"),
        # Triângulo de coorte sobre a janela observada; conferido por prototipagem
        # real em 2026-10-14 (12 coortes, 2017-01 .. 2017-12).
        expected_rows=84,
        gold_deps=("agg_household_activity_month",),
        description=(
            "Retenção por coorte (SECUNDÁRIA/DIDÁTICA, metrics.md §6.3). coorte = "
            "mês da PRIMEIRA cesta OBSERVADA do domicílio. *** LEFT-CENSORING: "
            "cohort_month é 'primeira aparição na janela', NÃO a aquisição real — a "
            "coorte de 2017-01 inchada é artefato do início dos dados, não 'novos "
            "de janeiro'. *** Cada domicílio em exatamente 1 coorte; months_since=0 "
            "tem retenção 1,0 por definição; o mês parcial 2018-01 subestima a última "
            "coluna de cada coorte (right-censoring). Observacional: sem causalidade."
        ),
        violation_checks=(
            ViolationCheck(
                name="retention_rate_in_unit_interval",
                description="Toda retention_rate em [0, 1].",
                where_expr="retention_rate < 0 OR retention_rate > 1",
            ),
            ViolationCheck(
                name="months_since_non_negative",
                description="months_since >= 0 (atividade nunca antes da coorte).",
                where_expr="months_since < 0",
            ),
            ViolationCheck(
                name="active_le_cohort_size",
                description="active_households <= cohort_size em toda linha.",
                where_expr="active_households > cohort_size",
            ),
            ViolationCheck(
                name="m0_is_full_retention",
                description="No mês da coorte (months_since=0) a retenção é 1,0 por definição.",
                where_expr="months_since = 0 AND retention_rate <> 1",
            ),
        ),
        integrity_checks=(
            IntegrityCheck(
                name="cohorts_partition_universe",
                description=(
                    "Soma dos cohort_size distintos por coorte == 2.469 (cada "
                    "domicílio em exatamente 1 coorte; união das coortes = universo)."
                ),
                # Retorna 1 (violação) se a soma das coortes não cobrir o universo.
                count_sql=f"""
                    SELECT COUNT(*) FROM (
                        SELECT SUM(cohort_size) AS total
                        FROM (SELECT DISTINCT cohort_month, cohort_size FROM {{this}})
                    ) WHERE total <> {HOUSEHOLD_UNIVERSE}
                """,
            ),
        ),
    ),
    # -----------------------------------------------------------------------
    # CAMPANHA / CUPOM (metrics.md §8, v1 factual 8.1–8.4). Ordem de construção
    # §8.7: bridge -> dim_campaign -> fct_coupon_redemption ->
    # agg_campaign_performance -> agg_coupon_redemption; + exposure por domicílio.
    # NENHUMA toca em sales_value (anti-fan-out §8.0.2).
    # -----------------------------------------------------------------------
    GoldSpec(
        name="bridge_household_campaign",
        transform_sql=_SQL_BRIDGE_HOUSEHOLD_CAMPAIGN,
        grain="1 domicílio × campanha (campaign_id, household_id)",
        grain_columns=("campaign_id", "household_id"),
        expected_rows=CAMPAIGN_EXPOSURE_ANCHOR,  # 6.589 pares (âncora §8.0.1)
        silver_deps=("campaigns",),
        description=(
            "Ponte N:N domicílio×campanha (quem foi ALVO de cada campanha; §8.3). "
            "Promovida de silver.campaigns. Base do não-fan-out: alcance/taxas "
            "derivam dela, nunca de join com transactions. Exposição = distribuição, "
            "NÃO engajamento (§8.0). 6.589 pares, 1.559 domicílios distintos."
        ),
        reconcile_checks=(
            ReconcileCheck(
                name="exposed_households_distinct",
                description="COUNT(DISTINCT household_id) == 1.559 (âncora §8.0.1).",
                value_expr="COUNT(DISTINCT household_id)",
                expected=float(EXPOSED_HOUSEHOLDS_ANCHOR),
                tol=0.0,
            ),
            ReconcileCheck(
                name="campaigns_distinct",
                description="COUNT(DISTINCT campaign_id) == 27 (todas as campanhas têm alvo).",
                value_expr="COUNT(DISTINCT campaign_id)",
                expected=float(CAMPAIGN_COUNT),
                tol=0.0,
            ),
        ),
    ),
    GoldSpec(
        name="dim_campaign",
        transform_sql=_SQL_DIM_CAMPAIGN,
        grain="1 campanha (campaign_id)",
        grain_columns=("campaign_id",),
        expected_rows=CAMPAIGN_COUNT,  # 27
        silver_deps=("campaign_descriptions",),
        gold_deps=("bridge_household_campaign",),
        description=(
            "Dimensão de campanha (§8.1/8.4): campaign_type ('Type A/B/C', valor "
            "real), start_date, end_date e households_exposed (alcance, §8.1). "
            "Alcance NÃO é aditivo: a soma das 27 dá 6.589 exposições, mas o "
            "universo alcançado é 1.559 domicílios distintos (§8.0.2)."
        ),
        reconcile_checks=(
            ReconcileCheck(
                name="sum_exposed_equals_bridge_rows",
                description="SUM(households_exposed) == 6.589 (pares da ponte; não é o universo).",
                value_expr="SUM(households_exposed)",
                expected=float(CAMPAIGN_EXPOSURE_ANCHOR),
                tol=0.0,
            ),
        ),
        violation_checks=(
            ViolationCheck(
                name="campaign_type_domain",
                description="campaign_type em {'Type A','Type B','Type C'} (domínio real §7).",
                where_expr="campaign_type NOT IN ('Type A', 'Type B', 'Type C')",
            ),
            ViolationCheck(
                name="households_exposed_positive",
                description="Toda campanha tem >= 1 domicílio exposto.",
                where_expr="households_exposed < 1",
            ),
        ),
    ),
    GoldSpec(
        name="agg_household_campaign_exposure",
        transform_sql=_SQL_AGG_HOUSEHOLD_CAMPAIGN_EXPOSURE,
        grain="1 domicílio exposto (household_id)",
        grain_columns=("household_id",),
        expected_rows=EXPOSED_HOUSEHOLDS_ANCHOR,  # 1.559
        gold_deps=("bridge_household_campaign",),
        description=(
            "Sobreposição de campanha por domicílio (§8.3): n_campaigns_exposed = "
            "nº de campanhas recebidas por lar (média 4,23; máx. 15). Habilita "
            "cruzar exposição × RFM (DESCRITIVO, não efeito; viés de seleção §8.3). "
            "Cobre só os 1.559 expostos."
        ),
        reconcile_checks=(
            ReconcileCheck(
                name="sum_exposures_equals_bridge_rows",
                description="SUM(n_campaigns_exposed) == 6.589 (total de exposições).",
                value_expr="SUM(n_campaigns_exposed)",
                expected=float(CAMPAIGN_EXPOSURE_ANCHOR),
                tol=0.0,
            ),
        ),
        violation_checks=(
            ViolationCheck(
                name="n_campaigns_exposed_positive",
                description="Todo domicílio da tabela recebeu >= 1 campanha.",
                where_expr="n_campaigns_exposed < 1",
            ),
        ),
    ),
    GoldSpec(
        name="fct_coupon_redemption",
        transform_sql=_SQL_FCT_COUPON_REDEMPTION,
        grain="1 evento de resgate (household_id, coupon_upc, campaign_id, redemption_date)",
        grain_columns=("household_id", "coupon_upc", "campaign_id", "redemption_date"),
        expected_rows=REDEMPTION_EVENT_ANCHOR,  # 2.102
        silver_deps=("coupon_redemptions", "campaign_descriptions"),
        description=(
            "Fato de evento de resgate (§8.4): 2.102 eventos com campaign_type por "
            "join. NÃO é multiplicador de receita (sem campo monetário; sem ligação "
            "à linha de venda, §8.0 verdade 3). Resgate = evento observado, NÃO "
            "conversão causada (§8.0 verdade 2)."
        ),
        reconcile_checks=(
            ReconcileCheck(
                name="redeemer_households_distinct",
                description="COUNT(DISTINCT household_id) == 410 (resgatadores, âncora §8.0.1).",
                value_expr="COUNT(DISTINCT household_id)",
                expected=float(REDEEMER_HOUSEHOLDS_ANCHOR),
                tol=0.0,
            ),
            ReconcileCheck(
                name="redeemed_coupons_distinct",
                description="COUNT(DISTINCT coupon_upc) == 491 (cupons resgatados, âncora §8.0.1).",
                value_expr="COUNT(DISTINCT coupon_upc)",
                expected=float(COUPONS_REDEEMED_ANCHOR),
                tol=0.0,
            ),
        ),
        violation_checks=(
            ViolationCheck(
                name="campaign_type_present",
                description="Todo evento tem campaign_type (FK campaign_id resolvida).",
                where_expr="campaign_type IS NULL",
            ),
        ),
        integrity_checks=(
            IntegrityCheck(
                name="fk_campaign_id_in_descriptions",
                description=(
                    "Todo campaign_id de resgate existe em campaign_descriptions "
                    "(FK válida)."
                ),
                count_sql="""
                    SELECT COUNT(*) FROM {this} f
                    WHERE NOT EXISTS (
                        SELECT 1 FROM {silver_campaign_descriptions} d
                        WHERE d.campaign_id = f.campaign_id
                    )
                """,
            ),
        ),
    ),
    GoldSpec(
        name="agg_campaign_performance",
        transform_sql=_SQL_AGG_CAMPAIGN_PERFORMANCE,
        grain="1 campanha (campaign_id)",
        grain_columns=("campaign_id",),
        expected_rows=CAMPAIGN_COUNT,  # 27
        gold_deps=("dim_campaign", "fct_coupon_redemption", "bridge_household_campaign"),
        description=(
            "Desempenho por campanha (§8.1/8.2): households_exposed, "
            "households_redeemed (distintos) e redemption_rate = redeemed/EXPOSTOS "
            "(household-level, ∈[0,1]). Denominador = expostos, nunca 'cupons "
            "enviados' (§8.2). Evento NUNCA é numerador de taxa. Observacional: "
            "resgate != conversão causada (§8.0)."
        ),
        reconcile_checks=(
            ReconcileCheck(
                name="sum_exposed_equals_bridge_rows",
                description="SUM(households_exposed) == 6.589 (consistência com a ponte).",
                value_expr="SUM(households_exposed)",
                expected=float(CAMPAIGN_EXPOSURE_ANCHOR),
                tol=0.0,
            ),
            ReconcileCheck(
                name="sum_redeemed_equals_redeemer_pairs",
                description="SUM(households_redeemed) == 792 (pares distintos domicílio×campanha).",
                value_expr="SUM(households_redeemed)",
                expected=float(REDEEMER_PAIRS_ANCHOR),
                tol=0.0,
            ),
        ),
        violation_checks=(
            ViolationCheck(
                name="redemption_rate_in_unit_interval",
                description="Toda redemption_rate em [0, 1].",
                where_expr="redemption_rate < 0 OR redemption_rate > 1",
            ),
            ViolationCheck(
                name="redeemed_le_exposed",
                description="households_redeemed <= households_exposed em toda linha.",
                where_expr="households_redeemed > households_exposed",
            ),
            ViolationCheck(
                name="households_exposed_positive",
                description="Toda campanha tem households_exposed > 0 (denominador válido).",
                where_expr="households_exposed < 1",
            ),
        ),
        integrity_checks=(
            IntegrityCheck(
                name="redeemers_subset_of_exposed",
                description=(
                    "Todo par (household_id, campaign_id) que resgatou existe na "
                    "ponte de expostos (numerador ⊆ denominador, §8.2)."
                ),
                count_sql="""
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT household_id, campaign_id
                        FROM {gold_fct_coupon_redemption}
                    ) x
                    WHERE NOT EXISTS (
                        SELECT 1 FROM {gold_bridge_household_campaign} b
                        WHERE b.household_id = x.household_id
                          AND b.campaign_id = x.campaign_id
                    )
                """,
            ),
        ),
    ),
    GoldSpec(
        name="agg_coupon_redemption",
        transform_sql=_SQL_AGG_COUPON_REDEMPTION,
        grain="1 tipo de campanha (campaign_type)",
        grain_columns=("campaign_type",),
        expected_rows=3,  # Type A / Type B / Type C
        gold_deps=("bridge_household_campaign", "dim_campaign", "fct_coupon_redemption"),
        description=(
            "Resgate por tipo de campanha A/B/C (§8.4): n_redemption_events (volume, "
            "aditivo => 2.102), households_redeemed e n_coupons_redeemed (distintos "
            "DENTRO do tipo, NÃO aditivos entre tipos) e redemption_rate = "
            "redeemed/expostos. Reportar a taxa, não só o volume (um tipo pode ter "
            "mais resgates só por ter sido enviado a mais gente)."
        ),
        reconcile_checks=(
            ReconcileCheck(
                name="events_sum_matches",
                description="SUM(n_redemption_events) == 2.102 (eventos são aditivos por tipo).",
                value_expr="SUM(n_redemption_events)",
                expected=float(REDEMPTION_EVENT_ANCHOR),
                tol=0.0,
            ),
        ),
        violation_checks=(
            ViolationCheck(
                name="campaign_type_domain",
                description="campaign_type em {'Type A','Type B','Type C'}.",
                where_expr="campaign_type NOT IN ('Type A', 'Type B', 'Type C')",
            ),
            ViolationCheck(
                name="redemption_rate_in_unit_interval",
                description="Toda redemption_rate em [0, 1].",
                where_expr="redemption_rate < 0 OR redemption_rate > 1",
            ),
            ViolationCheck(
                name="redeemed_le_exposed",
                description="households_redeemed <= households_exposed em todo tipo.",
                where_expr="households_redeemed > households_exposed",
            ),
        ),
    ),
)

GOLD_SPECS_BY_NAME: dict[str, GoldSpec] = {s.name: s for s in GOLD_SPECS}
