# Métricas Fundamentais — Camada Gold (Overview + base de CRM)

> Autor conceitual: **analytics-mentor**. Status: **APROVADO (2026-10-14)** — decisões 1–5 confirmadas pelo usuário (ver §7). O analytics-engineer está liberado para implementar o Gold.
> Base factual: `docs/data-model.md` (§3 fonte única da receita, §4 anti-fan-out, §5 tabelas Gold) e `docs/data-dictionary.md` (schema real). Nenhum campo é presumido.

---

## 0. Fundamentos que valem para TODAS as métricas

Antes de uma métrica a métrica, três âncoras fixas. Elas não se discutem — são fatos dos dados.

| Âncora | Valor | Origem |
|---|---|---|
| **Receita observada total** | **US$ 4.596.039,58** | `SUM(transactions.sales_value)` sobre as 1.469.307 linhas |
| **Data de referência (as-of / snapshot date)** | **2018-01-01** (fim da semana 53) | **Máxima** `transaction_timestamp` observada. **NUNCA** a data atual do computador (regra 8 do CLAUDE.md). |
| **Universo de domicílios** | **2.469** domicílios (`household_id` distintos em transactions) | Todos têm ≥ 1 cesta. Demografia cobre só 801 (32,4%). |

### 0.1 O que "receita observada" significa (escopo — leia antes de tudo)
É a receita **capturada pelo painel de domicílios** do estudo 84.51°/dunnhumby — uma **amostra** de ~2.469 lares de fidelidade, **não** o faturamento total da rede. Toda métrica monetária aqui descreve o comportamento **desta amostra**, não o mercado. Nunca apresente estes números como "vendas da empresa".

### 0.2 As flags da Silver e a decisão-mestre de filtro
A Silver já marcou (não removeu) quatro situações em `transactions`:

| Flag | Linhas | O que é | Afeta qual métrica |
|---|---|---|---|
| `is_zero_qty` | 8.869 | `quantity = 0` (estorno/ajuste/registro técnico) | contagem de itens, não receita |
| `is_free_item` | 11.226 | item gratuito (brinde/cupom 100%) → `sales_value` tende a 0 | contagem de itens; some 0 à receita |
| `is_weighted` | 13.494 | item vendido por peso (`quantity` é peso, não unidades) | qualquer soma de `quantity` |
| `is_orphan_product` | 4.836 | `product_id` sem cadastro em `products` | joins com `dim_product`, não receita |

**Regra-mestre (PROPOSTA que recomendo aprovar):** a métrica **"Receita observada" inclui TODAS as linhas, sem exceção** — porque a âncora US$ 4.596.039,58 é a soma de tudo. **Qualquer filtro quebra a reconciliação com a âncora.** Filtros (excluir `is_zero_qty` etc.) só se aplicam a métricas de **contagem/comportamento** (itens por cesta, quantidade), nunca ao headline de receita. Isto é o oposto do instinto júnior de "limpar antes de somar".

### 0.3 Por que o grão importa tanto (a regra que evita 90% dos erros)
A fato é **item-de-linha** (`basket_id`, `product_id`). As métricas vivem em grãos diferentes e **só se sobe, nunca se desce**:

```
item-de-linha (1.469.307)  →  cesta (155.848)  →  domicílio (2.469)  →  coorte
   fct_transaction_line        fct_basket          agg_household_rfm
```
O erro clássico é calcular no grão errado (ex.: `AVG(sales_value)` dá o valor médio **da linha** ~US$ 3,13, que **não é** ticket médio de cesta ~US$ 29,49). Cada métrica abaixo declara seu grão **explicitamente**.

---

## 1. Receita observada (total e por semana)

**Definição (1 frase):** soma do dinheiro efetivamente recebido pelo varejista, nas cestas dos domicílios do painel, num recorte de tempo.

| Campo | Especificação |
|---|---|
| **Numerador** | `SUM(sales_value)` |
| **Denominador** | — (é um total, não uma razão) |
| **Grão de cálculo** | item-de-linha, agregado para o recorte pedido (total, por `week`, por `store_id`) |
| **Unidade de análise de saída** | período (total) ou semana (`agg_weekly_revenue`) |
| **Janela temporal** | semanas 1–53 (2017-01-01 → 2018-01-01); por semana para a série temporal |
| **Data de referência** | não aplica recência; o período é a própria janela observada |
| **Filtros** | **nenhum** — inclui `is_zero_qty`, `is_free_item` (somam 0), `is_weighted`, `is_orphan_product`. Ver §0.2. |
| **Fonte única** | `transactions` apenas. **Nunca** somar `sales_value` após join com promotions/coupons/campaigns (fan-out, ver data-model §4). |

- **Tabela Gold:** `agg_weekly_revenue` (grão `week`, opcionalmente × `store_id`): `revenue`, `n_baskets`, `n_active_households`. O total do Overview é a soma desta tabela.
- **Asset check:** `revenue_reconciles` — `SUM(agg_weekly_revenue.revenue)` deve ser **exatamente US$ 4.596.039,58**. Qualquer desvio = fan-out ou filtro indevido.
- **Limitações / armadilhas:**
  - É receita **da amostra**, não da rede (§0.1).
  - `sales_value` **já é líquido** de `retail_disc` e cupom aplicado no caixa — **não** reconstruir "receita cheia" somando descontos (isso é *list value*, outra métrica).
  - Semana 53 e semana 1 podem ser **parciais** no calendário — não interprete sua receita menor como queda de demanda.
  - Receita **não atribuível a campanha/cupom** sem aproximação (transactions tem `coupon_disc>0` mas não o `coupon_upc`).

---

## 2. Domicílios ativos

**Definição (1 frase):** número de domicílios distintos que realizaram ao menos uma compra no recorte de tempo.

| Campo | Especificação |
|---|---|
| **Numerador** | `COUNT(DISTINCT household_id)` com ≥ 1 cesta no período |
| **Denominador** | — (contagem). Para **taxa de atividade**: dividir pelos 2.469 do universo |
| **Grão de cálculo** | domicílio |
| **Janela temporal** | o recorte pedido (total do ano, mês, ou `week`) |
| **Data de referência** | 2018-01-01 só se a definição for "ativo nos últimos N dias" (ver nota) |
| **Filtros** | **PROPOSTA:** "ativo" = tem ≥ 1 `basket_id` no período. Não exigir receita > 0 (uma cesta só de item grátis ainda é uma visita). |
| **Decisão aberta** | Exigir receita > 0 para contar como ativo? Recomendo **não** (atividade = visita, não gasto), mas é decisão sua. |

- **Definição de "ativo":** há duas escolas — (a) **atividade por janela fixa** (ativo no mês M = comprou em M); (b) **atividade por recência** (ativo = comprou nos últimos 30/90 dias contados de 2018-01-01). Para o Overview recomendo **(a) por janela** (mais intuitivo numa série); a recência fica na métrica RFM (§5).
- **Tabela Gold:** `agg_weekly_revenue.n_active_households` (ativos por semana) e um total no card do Overview.
- **Asset check:** `active_hh_within_universe` — ativos em qualquer período ≤ 2.469; total anual de distintos = 2.469 (todos compraram ao menos uma vez no ano).
- **Limitações / armadilhas:**
  - **Domicílio ≠ pessoa** (regra 3): um lar pode ter vários moradores; "ativos" conta lares, não consumidores.
  - **Somar ativos de várias semanas ≠ ativos do período** (um domicílio ativo em 10 semanas contaria 10×). Ativos é sempre `DISTINCT` na janela pedida — **não** é aditivo entre janelas.
  - Left-censoring: não sabemos se um domicílio estava "inativo e voltou" antes de 2017 — não há histórico pré-janela.

---

## 3. Nº de cestas e frequência de compra

**Definição (1 frase):** cestas = número de compras distintas (tickets); frequência = quantas cestas um domicílio faz no período.

| Campo | Nº de cestas | Frequência (por domicílio) |
|---|---|---|
| **Numerador** | `COUNT(DISTINCT basket_id)` | `COUNT(DISTINCT basket_id)` do domicílio |
| **Denominador** | — | — (é contagem por domicílio); média = cestas ÷ domicílios ativos |
| **Grão** | cesta | domicílio |
| **Janela** | recorte pedido | período completo (ou janela RFM) |
| **Data de referência** | — | 2018-01-01 se "frequência nos últimos N dias" |
| **Filtros** | **nenhum** no headline (mantém reconciliação). Uma cesta existe mesmo que só contenha item grátis. | idem |

- **Ordem de grandeza (sanity check):** 155.848 cestas ÷ 2.469 domicílios ≈ **63 cestas/domicílio/ano** (≈ 1,2/semana). Coerente com **supermercado** (compra recorrente). Se der 3 ou 300, há erro de grão.
- **Tabela Gold:** `fct_basket` (grão 1 cesta: `basket_id`, `household_id`, `store_id`, `transaction_timestamp`, `n_items`, `basket_revenue`). Frequência agrega `fct_basket` por domicílio → alimenta o **F** do RFM.
- **`n_items` por cesta — decisão de grão:** **PROPOSTA:** `n_items = COUNT(*)` (nº de linhas/produtos distintos na cesta), **não** `SUM(quantity)`. Motivo: `quantity` mistura unidades e **peso** (`is_weighted`) — somar daria "9 + 2,5 kg". Para "quantos produtos levou", conte linhas.
- **Asset check:** `basket_count_matches` — `COUNT(DISTINCT basket_id)` em `fct_basket` = **155.848**; `SUM(n_items)` = **1.469.307** (total de linhas).
- **Limitações / armadilhas:**
  - **Cesta ≠ item.** Confundir `COUNT(*)` de linhas com nº de cestas infla a frequência ~9×.
  - Frequência é **enviesada à direita** (poucos domicílios muito frequentes) — reporte **mediana** além da média.
  - Uma "cesta" é um `basket_id`; devoluções/ajustes não têm tabela separada aqui, então uma cesta pode conter linha com `sales_value` baixo/zero.

---

## 4. Ticket médio por cesta (Average Basket Value)

**Definição (1 frase):** valor médio gasto por cesta (por visita de compra).

| Campo | Especificação |
|---|---|
| **Numerador** | `SUM(sales_value)` = receita observada |
| **Denominador** | `COUNT(DISTINCT basket_id)` = nº de cestas |
| **Grão de cálculo** | **cesta** (razão receita÷cestas) — **jamais** a linha |
| **Unidade de saída** | moeda por cesta |
| **Janela** | recorte pedido (total, mês, semana) |
| **Data de referência** | — |
| **Filtros** | **nenhum** no headline (usa a mesma receita e cestas reconciliadas) |

- **Ordem de grandeza:** 4.596.039,58 ÷ 155.848 ≈ **US$ 29,49/cesta**. Coerente com compra de mercado. Se aparecer ~US$ 3,13, alguém calculou `AVG(sales_value)` **no grão de linha** — erro clássico.
- **Duas formas equivalentes (e uma errada):**
  - ✅ **Ratio:** `SUM(sales_value) / COUNT(DISTINCT basket_id)` — robusto.
  - ✅ **Média dos totais de cesta:** `AVG(basket_revenue)` calculado **sobre `fct_basket`** (média de uma linha por cesta). Dá o mesmo número.
  - ❌ **`AVG(sales_value)` sobre `transactions`:** média do item de linha, **não** da cesta. Errado.
- **Tabela Gold:** derivada de `fct_basket` (`AVG(basket_revenue)`); no Overview, um card. Por semana, vem de `agg_weekly_revenue` (`revenue / n_baskets`).
- **Asset check:** `abv_consistency` — `AVG(fct_basket.basket_revenue)` ≈ `revenue_total / n_baskets` (diferença só por arredondamento).
- **Limitações / armadilhas:**
  - **Média é sensível a cestas gigantes** (o range de `sales_value` por linha vai até 840; uma cesta de estoque mensal distorce). **Reporte também a mediana** do `basket_revenue`.
  - ABV mistura perfis (abastecimento grande vs. compra de conveniência) — segmentar por nº de itens é mais informativo que a média global.

---

## 5. RFM — Recência, Frequência, Valor monetário

**Definição (1 frase):** três eixos que resumem o valor de um domicílio — **quão recentemente** comprou, **com que frequência** e **quanto gastou** — combinados num score de segmentação.

**Esta é a base do CRM.** Grão de saída: **1 linha por domicílio** (`agg_household_rfm`, os 2.469).

### 5.1 As três dimensões

| Dimensão | Definição | Cálculo | Direção (melhor) |
|---|---|---|---|
| **Recência (R)** | dias desde a última compra | `DATEDIFF(day, MAX(transaction_timestamp)::date, '2018-01-01')` por domicílio | **menor = melhor** (comprou há pouco) |
| **Frequência (F)** | nº de cestas no período | `COUNT(DISTINCT basket_id)` por domicílio | maior = melhor |
| **Valor monetário (M)** | receita observada do domicílio | `SUM(sales_value)` por domicílio | maior = melhor |

| Parâmetro | Valor |
|---|---|
| **Data de referência (as-of)** | **2018-01-01** — a máxima data observada. Recência medida a partir daqui, **nunca** da data atual. |
| **Janela** | período completo (semanas 1–53). Mesma janela para R, F e M (comparabilidade). |
| **Grão** | domicílio |
| **Filtros** | **nenhum** para R e M no headline (reconciliam). F usa `DISTINCT basket_id` (ver §3). |
| **Universo** | os 2.469 domicílios (todos têm ≥ 1 cesta → R, F, M sempre definidos). |

### 5.2 Scoring (PROPOSTA — requer aprovação)

- **Método:** **quintis via `NTILE(5)`** em cada dimensão → score 1–5. **R invertido** (recência menor → score 5). F e M: maior → 5.
- **Tamanho do quintil:** 2.469 ÷ 5 ≈ **494 domicílios** por faixa.
- **Score combinado:** célula **R-F-M** (ex.: `555` = melhor; `111` = pior) → 125 células. Para o Overview, agrupar em **segmentos nomeados**.
- **Tabela de segmentos (APROVADA 2026-10-14):** avaliar na ordem de cima para baixo; a primeira regra satisfeita define o segmento (mutuamente exclusivos por precedência).

  | Segmento | Regra (quintis 1–5) | Leitura |
  |---|---|---|
  | **Campeões** | R≥4 e F≥4 e M≥4 | compram recente, sempre, gastam muito |
  | **Leais** | F≥4 e M≥3 | alta frequência/valor (R qualquer) |
  | **Potenciais** | R≥4 e F entre 2–3 | recentes, construindo hábito |
  | **Novos** | R=5 e F≤2 | compraram agora, pouca história |
  | **Em risco** | R≤2 e F≥3 e M≥3 | eram bons, esfriando |
  | **Hibernando / Perdidos** | R≤2 e F≤2 | inativos de baixo valor |
  | **Outros** | (nenhuma das acima) | casos intermediários — reportar como resíduo, não forçar rótulo |

  > A precedência importa: um domicílio R5/F4/M4 cai em **Campeões** (primeira regra), não em Leais. O bucket **Outros** é esperado e saudável — não invente um nome para cada célula das 125.
- **Ressalvas do scoring (críticas):**
  - **Empates na recência:** muitos domicílios têm a mesma data de última compra (ex.: todos que compraram na semana 53). `NTILE` **quebra empates arbitrariamente** — dois domicílios idênticos podem cair em quintis diferentes. Mitigar: documentar; ou usar faixas de dias fixas em vez de quintis.
  - **Distribuição enviesada:** F e M são **fortemente assimétricos à direita** (cauda de domicílios muito valiosos). Quintis por `NTILE` resolvem a assimetria melhor que cortes fixos, mas cuidado ao interpretar "quintil 5 de M" — concentra muito mais receita que 1/5.
  - **Supermercado comprime a Frequência:** com ~63 cestas/ano de média, a maioria dos domicílios é frequente; o quintil 1 de F ainda pode ter dezenas de cestas. F discrimina menos que num varejo de compra esporádica.
  - **Amostra pequena (2.469):** quintis de ~494 são estáveis, mas segmentos cruzados (125 células) ficam esparsos — use os segmentos nomeados agregados, não as 125 células cruas, no Overview.

### 5.3 RFM **não** herda o viés demográfico — ponto importante

RFM é **comportamental** (vem de transactions, que cobre 100% dos 2.469 domicílios). O viés de cobertura de 32,4% é da **demografia** (`dim_household`). Logo: **segmentar por RFM é não-enviesado por cobertura**; **cruzar RFM com idade/renda** reintroduz o viés (só 801 têm demografia) — nesse cruzamento, sempre reporte "base = 801" e rotule como amostra parcial.

- **Tabela Gold:** `agg_household_rfm` (grão domicílio): `recency_days`, `frequency_baskets`, `monetary_value`, `r_score`, `f_score`, `m_score`, `rfm_segment`.
- **Asset checks:**
  - `rfm_monetary_reconciles` — `SUM(agg_household_rfm.monetary_value)` = **US$ 4.596.039,58** (M é partição exata da receita).
  - `rfm_frequency_reconciles` — `SUM(frequency_baskets)` = **155.848** cestas.
  - `rfm_row_count` — exatamente **2.469** linhas (uma por domicílio, sem perda nem duplicação).
  - `rfm_recency_bounds` — `recency_days` ∈ [0, 365]; nenhum negativo (negativo = usou data de referência errada).
- **Limitações / armadilhas:**
  - **Left-censoring:** "última compra na semana 53" é relativo ao fim dos **dados**, não ao fim do relacionamento. Não conclua "cliente perdido" de R alto — a janela simplesmente acabou.
  - **Monetário é da amostra**, não lifetime value real (sem histórico completo nem margem).
  - RFM é **descritivo**, não preditivo — não afirma que o quintil 5 "vai" continuar comprando.

---

## 6. Retenção e recompra

**Definição (1 frase):** retenção mede se domicílios que compraram num período **voltam** a comprar em períodos seguintes; recompra é o fato de um domicílio ter **≥ 2 cestas**.

**Aviso central:** aqui tudo é **observacional**. Não há grupo de controle nem intervenção — mede-se a **cadência natural** da amostra, não o efeito de nenhuma ação. **Correlação ≠ causalidade** (regra 9).

### 6.1 Recompra (repurchase) — a métrica simples

| Campo | Especificação |
|---|---|
| **Definição** | domicílio com `COUNT(DISTINCT basket_id) ≥ 2` no período |
| **Numerador** | nº de domicílios com ≥ 2 cestas |
| **Denominador** | nº de domicílios ativos no período |
| **Grão** | domicílio |
| **Janela** | período completo (ou mês, para recompra mensal) |

- **Esperado:** em supermercado, a recompra anual é **~100%** (média de 63 cestas). Portanto, no período anual, recompra binária **quase não discrimina** — é um sanity check, não um KPI. Mais útil: **tempo médio entre compras** (inter-purchase time) ou recompra em **janela curta** (ex.: recomprou dentro de 30 dias).

### 6.2 Retenção período-a-período (PROPOSTA recomendada p/ o Overview)

| Campo | Especificação |
|---|---|
| **Definição** | % de domicílios ativos no período P que também estão ativos em P+1 |
| **Numerador** | domicílios ativos em P **e** em P+1 |
| **Denominador** | domicílios ativos em P |
| **Grão** | domicílio; granularidade de período = **mês** (recomendado) ou semana |
| **Data de referência** | não usa as-of; usa fronteiras de período dentro de 2017 |
| **Filtros** | ativo = ≥ 1 cesta no período (consistente com §2) |

- **Por que mês e não semana:** semana a semana, a retenção oscila muito (nem todo lar compra toda semana, mesmo sendo fiel). Mês suaviza a cadência natural e é o padrão de leitura executiva.

### 6.3 Coorte de retenção (secundária / didática — com ressalvas fortes)

| Campo | Especificação |
|---|---|
| **Definição** | agrupar domicílios pelo **mês da primeira cesta observada** e medir a % ativa em cada mês subsequente (triângulo de coorte) |
| **Grão** | domicílio × mês-da-coorte × mês-de-atividade |
| **Data de referência** | primeira e última cesta por domicílio, dentro de 2017 |

- **Limitação que invalida a leitura ingênua — LEFT-CENSORING:** a "primeira cesta observada" **não é** a aquisição real do cliente. O dataset começa em 2017-01-01; **a maioria dos domicílios aparece na coorte de janeiro só porque é onde os dados começam**, não porque foram adquiridos ali. Portanto, a coorte de janeiro **não é** "novos clientes de janeiro" — é "todos os já-clientes visíveis no início". Só coortes de meses **posteriores** (ex.: primeira compra em junho) se aproximam de "novos", e ainda assim podem ser clientes antigos que ficaram inativos no começo da janela. **Rotular explicitamente como coorte de *primeira aparição na janela*, não de aquisição.**
- **Right-censoring:** coortes tardias têm menos meses para maturar — não compare retenção de M12 entre coorte de jan e de out.

- **Tabela Gold:** `agg_household_rfm` já dá `recency_days` e `frequency_baskets` (base de recompra). Retenção período-a-período e coortes pedem uma visão por domicílio × mês (derivável de `fct_basket`; candidata `agg_household_activity_month`, a propor na próxima rodada).
- **Asset check:** `retention_bounds` — toda taxa ∈ [0, 1]; denominador de P = ativos de P (bate com §2); coorte não soma domicílio em duas coortes (cada household tem exatamente um mês de primeira aparição).
- **Limitações / armadilhas (resumo):**
  - **Sem causalidade.** Retenção observada ≠ efeito de CRM. Nunca diga "nossa ação reteve X%".
  - **Left/right-censoring** (acima) distorce coortes.
  - **Domicílio ≠ pessoa:** um lar pode "sair" porque mudou de loja/cartão, não por churn real.
  - **Eventos de CRM sintéticos** (abertura de e-mail, clique, push) **não existem** nestes dados reais; se forem simulados depois, rotular como **simulado** e jamais misturar com retenção real sem aviso.

---

## 7. Resumo — o que implementar PRIMEIRO no Gold (e por quê)

Ordem recomendada, por dependência e valor para o Overview:

| Ordem | Tabela Gold | Entrega | Por quê primeiro |
|---|---|---|---|
| **1º** | `fct_basket` | grão cesta: `basket_id`, household, store, timestamp, `n_items`, `basket_revenue` | **Pedra fundamental.** Dela saem cestas (§3), ticket médio (§4) e a frequência do RFM (§5). Reconcilia a receita e o nº de cestas. Nada sério roda sem ela. |
| **2º** | `agg_weekly_revenue` | grão semana: `revenue`, `n_baskets`, `n_active_households` | Alimenta **todos os cards e a série temporal do Overview** (§1, §2, §4). Barato de derivar de `fct_basket`. Carrega o asset check da âncora de receita. |
| **3º** | `agg_household_rfm` | grão domicílio: R, F, M + scores + segmento | **Base de CRM** (§5). Depende de `fct_basket`. Habilita segmentação — o maior valor analítico do projeto. Exige **aprovar o scoring e os nomes de segmento** antes. |
| **4º** | `agg_household_activity_month` (a propor) | domicílio × mês ativo | Só então retenção/coortes (§6), que são as mais sujeitas a interpretação errada — valem mais depois que os fundamentos estão validados. |

**Princípio da sequência:** construir de baixo (fato de cesta) para cima (domicílio → coorte), cada camada reconciliando com a âncora de receita e com as contagens (155.848 cestas, 2.469 domicílios) antes de seguir. **Receita e cestas primeiro (fáceis de validar), RFM depois (exige decisão de scoring), retenção por último (exige mais cuidado interpretativo).**

### Decisões — APROVADAS pelo usuário em 2026-10-14 ✅
1. **Receita = todas as linhas, sem filtro** (reconcilia a âncora US$ 4.596.039,58). ✅ aprovado.
2. **"Ativo" = ≥ 1 cesta, sem exigir receita > 0.** ✅ aprovado.
3. **`n_items` = contagem de linhas, não `SUM(quantity)`.** ✅ aprovado.
4. **RFM por quintis `NTILE(5)`, R invertido**, com os segmentos nomeados da tabela em §5.2. ✅ aprovado.
5. **Retenção: período-a-período mensal como primária; coorte só como secundária/didática** com o rótulo de left-censoring. ✅ aprovado.

> Status do documento: **APROVADO para implementação.** O analytics-engineer está liberado para construir o Gold na ordem da §7.

---

### Mentoria rápida (fecho)
1. **Problema de negócio:** o Overview responde "quanto a base comprou, quantos lares, com que frequência e quanto por visita"; o RFM responde "quais lares valem mais e quais estão esfriando".
2. **Conceito CRM:** o átomo é a linha de venda; sobe-se para cesta (comportamento de visita), domicílio (valor do cliente) e coorte (retenção). Nunca se desce de grão.
3. **Como os dados entram:** uma única fato (`transactions`) → `fct_basket` → `agg_household_rfm`; dimensões (produto, loja, campanha) só enriquecem, nunca somam receita.
4. **Por que estas definições:** cada grão e janela foi escolhido para (a) reconciliar com a âncora US$ 4.596.039,58 e (b) refletir a cadência de **supermercado** (compra recorrente), não de varejo esporádico.
5. **Erro júnior a evitar:** calcular ticket médio no grão de linha, somar receita após join, usar a data de hoje para recência, e ler coorte de janeiro como "aquisição".
6. **Como validar (sanity checks):** receita = 4.596.039,58; cestas = 155.848 (~63/domicílio); itens = 1.469.307 (~9,4/cesta); ticket ≈ US$ 29,49; domicílios ≤ 2.469; recência ∈ [0, 365]. Qualquer número que contradiga uma âncora está errado por construção.

---

# 8. Campanha e Cupom (Marketing Analytics) — **APROVADO (2026-10-14): só o factual 8.1–8.4**

> Autor conceitual: **analytics-mentor**. Status: **APROVADO em 2026-10-14 — escopo v1 = apenas as métricas FACTUAIS 8.1, 8.2, 8.3 e 8.4.** O usuário decidiu **NÃO implementar** a receita influenciada (§8.5) nem o pré/pós-campanha (§8.6) na v1, por falta de suporte honesto nos dados (ver motivos nessas subseções). O analytics-engineer está liberado para codar **somente 8.1–8.4**.
> Base factual: `docs/data-dictionary.md` (§§4–7: `coupons`, `coupon_redemptions`, `campaigns`, `campaign_descriptions`) e `docs/data-model.md` (§4 anti-fan-out, §4 limitação de atribuição). Nenhum campo é presumido.

## 8.0 O aviso que governa TODA esta seção (leia antes de tudo)

Esta é a área **analiticamente mais perigosa** do projeto. Três verdades inegociáveis, que repetirei em cada métrica:

1. **Exposição ≠ efeito.** `campaigns` diz que um domicílio **foi alvo** de uma campanha (recebeu o envio). **Não** diz que ele abriu, viu, leu ou reagiu. "Alcance" é um fato de *distribuição*, nunca de *engajamento* nem de *resultado*.
2. **Resgate ≠ conversão causada.** Um domicílio que resgatou um cupom muito provavelmente já compraria o produto (viés de autosseleção: quem resgata é quem já ia comprar). Resgate é um **evento observado**, não a prova de que a campanha **causou** a venda.
3. **Atribuição de receita a cupom é ESTIMATIVA, nunca fato.** `transactions` registra `coupon_disc > 0` (21.889 linhas) mas **não registra qual `coupon_upc`**. Logo, não existe ligação factual entre uma linha de receita e um cupom/campanha específico. Qualquer "receita de campanha" é uma **aproximação com forte risco de erro** — e sem grupo de controle, **jamais** é causal (regra 9 do CLAUDE.md).

> **Armadilha de reconciliação dos dois sinais de cupom (crítica).** Existem DOIS sinais de cupom nos dados e **eles não são a mesma coisa**:
> - `coupon_redemptions` = **2.102** eventos de resgate dos cupons **deste estudo** (com `coupon_upc`, sem valor em $).
> - `transactions.coupon_disc > 0` = **21.889** linhas com desconto de cupom **de fabricante em geral** (com valor em $, sem `coupon_upc`).
>
> Os números **não batem** (2.102 ≠ 21.889) porque `coupon_disc` capta **qualquer** cupom de fabricante, não só os 981 cupons das 27 campanhas do estudo. **Nunca** trate `coupon_disc > 0` como "resgate de campanha", nem some os dois. São populações diferentes.

### 8.0.1 Âncoras factuais desta seção (fatos dos dados — não se discutem)

| Âncora | Valor | Origem |
|---|---|---|
| **Exposições (linhas da ponte)** | **6.589** | `campaigns` (grão domicílio×campanha), 0 duplicatas |
| **Domicílios expostos (distintos)** | **1.559** (= **63,1%** dos 2.469) | `COUNT(DISTINCT household_id)` em `campaigns` |
| **Campanhas** | **27** (tipos A/B/C) | `campaign_descriptions` |
| **Média de campanhas por domicílio exposto** | **4,23** (máx. 15) | 6.589 ÷ 1.559 |
| **Cupons distintos / produtos elegíveis** | **981** cupons / **41.857** produtos | `coupons` (111.332 linhas após dedupe) |
| **Eventos de resgate** | **2.102** | `coupon_redemptions` |
| **Domicílios que resgataram (distintos)** | **410** (= **26,3%** dos 1.559 expostos; **16,6%** do painel) | `COUNT(DISTINCT household_id)` em `coupon_redemptions` |
| **Cupons resgatados (distintos)** | **491** de 981 | `coupon_redemptions` |
| **Janela das campanhas** | **2016-11-14 → 2018-02-28** | `campaign_descriptions` — **excede** a janela de transações (2017) |
| **Janela dos resgates** | **2017-01-01 → 2017-12-31** | `coupon_redemptions` — **dentro** da janela de vendas |

> **Observação temporal que condena a análise de receita por janela:** as campanhas começam antes e terminam depois dos dados de venda. Campanhas iniciadas em 2016 ou encerradas em fev/2018 têm a janela **truncada** pelos limites de `transactions` — não há como medir o período pré/durante/pós completo delas. Os **resgates**, por sorte, caem todos dentro de 2017, então as métricas factuais de resgate são seguras; as de **receita por janela**, não.

### 8.0.2 Regra de ouro anti-fan-out, reforçada para campanha/cupom

Reafirma a §4 do `data-model.md`. Três fan-outs específicos desta área:

| Join perigoso | Por que infla | Regra segura |
|---|---|---|
| `transactions × campaigns` por `household_id` | domicílio tem ~4,23 campanhas → cada linha de venda multiplica por ~4 | nunca somar receita após esse join; filtrar `household_id IN (público)` e somar a fato **antes** |
| `transactions × coupons` por `product_id` | produto aparece em vários cupons/campanhas | usar `coupons` só para montar **listas de elegibilidade**, nunca para somar receita |
| **somar entre campanhas** (produtos elegíveis, receita, resgates por produto) | **151 cupons pertencem a >1 campanha**; produtos se repetem entre campanhas → somar o total das 27 campanhas conta o mesmo produto/linha várias vezes | métricas por campanha **não são aditivas** num total; o total de domicílios/produtos/receita é sempre `DISTINCT`, nunca `SUM` das campanhas |

> **O erro que isto evita:** "a soma do alcance das 27 campanhas é 6.589, logo alcançamos 6.589 domicílios." **Errado** — são **1.559** domicílios distintos (muitos receberam várias campanhas). Alcance por campanha soma 6.589 *exposições*; o universo alcançado é 1.559 *domicílios*.

---

## 8.1 Alcance de campanha (reach) — **FACTUAL ✅**

**Definição (1 frase):** número de domicílios distintos que foram **alvo** (receberam o envio) de uma dada campanha.

| Campo | Especificação |
|---|---|
| **Numerador** | `COUNT(DISTINCT household_id)` em `campaigns` para a campanha |
| **Denominador** | — (é uma contagem). Para **taxa de cobertura**: dividir por 2.469 (painel) ou por 1.559 (universo exposto) — ver §8.3 |
| **Grão de cálculo** | **campanha** (1 linha por campanha) |
| **Janela temporal** | a ponte `campaigns` é **atemporal** (é uma lista de alvos); a janela vem de `campaign_descriptions` (`start_date`/`end_date`) só para contexto |
| **Data de referência** | não aplica (é distribuição, não recência) |
| **Filtros** | nenhum — a ponte não tem linhas a excluir |
| **Tabela Gold candidata** | `agg_campaign_performance` (grão 1 campanha): `campaign_id`, `campaign_type`, `start_date`, `end_date`, `n_households_exposed`, … |
| **Asset check** | `reach_bounds` — `SUM(n_households_exposed)` sobre as 27 campanhas = **6.589** (linhas da ponte); `COUNT(DISTINCT household_id)` global = **1.559** ≤ 2.469 |

- **Por que é factual:** `campaigns` é um registro de distribuição confirmado — não há inferência. É a métrica mais segura desta seção.
- **Limitações explícitas:**
  - **Alcance ≠ impressão ≠ engajamento.** "Foi alvo" não é "viu". Não há dado de abertura/clique (seria **sintético** se criado — rotular como simulado, regra do CLAUDE.md; nunca misturar com estes números reais).
  - **Alcance não é aditivo entre campanhas** (§8.0.2). Reportar alcance por campanha **e** o universo distinto (1.559) separadamente.

---

## 8.2 Taxa de resgate de cupom — **FACTUAL ✅ (com definição cuidadosa do denominador)**

**Definição (1 frase):** proporção de domicílios expostos a uma campanha que resgataram **pelo menos um** cupom dela.

> **A decisão difícil é o denominador. O que é "enviado" aqui?** Os dados **não têm** um log de "cupom X enviado ao domicílio Y". Têm: (a) quais domicílios receberam quais **campanhas** (`campaigns`), e (b) quais **cupons** pertencem a cada campanha (`coupons`). Supor que "cada um dos N cupons da campanha foi individualmente enviado a cada domicílio exposto" é uma **inflação não verificável** do denominador. Por isso **rejeito o denominador "resgates ÷ cupons enviados"** e defino a taxa no grão em que o dado é real: a **oferta de campanha** (par domicílio×campanha).

Proponho **duas taxas honestas**, em grãos diferentes:

### 8.2.a Taxa de resposta por campanha (household-level) — **PRIMÁRIA**

| Campo | Especificação |
|---|---|
| **Numerador** | `COUNT(DISTINCT household_id)` que resgataram ≥ 1 cupom **na campanha C** (de `coupon_redemptions` filtrado por `campaign_id`) |
| **Denominador** | `COUNT(DISTINCT household_id)` **expostos à campanha C** (de `campaigns`) |
| **Grão de cálculo** | **campanha** |
| **Janela** | resgates em 2017 (todos caem dentro); exposição é atemporal |
| **Filtros** | binário por domicílio (resgatou sim/não) — **não** contar eventos aqui |
| **Tabela Gold** | `agg_campaign_performance`: `n_households_redeemed`, `redemption_rate_hh = n_households_redeemed / n_households_exposed` |

### 8.2.b Taxa de resposta por oferta (par domicílio×campanha) — **SECUNDÁRIA / global**

| Campo | Especificação |
|---|---|
| **Numerador** | nº de pares `(household_id, campaign_id)` **distintos** presentes em `coupon_redemptions` |
| **Denominador** | **6.589** (pares domicílio×campanha ofertados = linhas de `campaigns`) |
| **Grão de cálculo** | oferta (par domicílio×campanha); pode agregar por `campaign_type` |
| **Tabela Gold** | `agg_campaign_performance` (por campanha) ou `agg_coupon_redemption` (por tipo) |

- **Ordem de grandeza (sanity check global):** 410 domicílios resgataram de 1.559 expostos ≈ **26,3%** resgataram ao menos uma vez; 2.102 eventos ÷ 410 domicílios ≈ **5,1 resgates por domicílio resgatador**. Se a "taxa" aparecer > 100% ou os eventos forem usados como numerador sobre domicílios, há erro de grão.
- **O erro júnior explícito a evitar:** dividir **2.102 eventos** por **1.559 domicílios** e chamar de "taxa de resgate de 135%". Evento não é domicílio; um lar resgata vários cupons. Taxas são sempre **binárias por domicílio** (resgatou/não) ou por **oferta** (par distinto); contagem de eventos é **volume**, nunca numerador de uma taxa sobre domicílios.
- **Asset checks:**
  - `redemption_rate_bounds` — toda taxa ∈ [0, 1].
  - `redeemers_subset_of_exposed` — todo `(household_id, campaign_id)` de `coupon_redemptions` **existe** em `campaigns` (numerador ⊆ denominador). Se não, é violação de integridade a reportar (WARN), não a esconder.
  - `redeemers_global` — `COUNT(DISTINCT household_id)` em resgates = **410** ≤ 1.559.
- **Limitações explícitas:**
  - **Resgate ≠ conversão causada** (§8.0, verdade 2): autosseleção. Não dizer "a campanha converteu 26%".
  - **Resgate não carrega valor em $** (a tabela não tem campo monetário) — não dá para somar "valor resgatado" sem estimativa (ver §8.5).
  - Cupom pode pertencer a >1 campanha (151 casos); o resgate traz o `campaign_id`, então o grão campanha fica íntegro — mas **não** somar resgates "por cupom" entre campanhas.

---

## 8.3 Participação e sobreposição de campanha — **FACTUAL ✅**

**Definição (1 frase):** quanto do painel foi atingido por campanhas e quão concentradas estão as campanhas em poucos domicílios.

| Campo | Especificação |
|---|---|
| **Cobertura do universo** | `1.559 / 2.469` = **63,1%** dos domicílios do painel foram alvo de ≥ 1 campanha |
| **Numerador** | `COUNT(DISTINCT household_id)` expostos (1.559) |
| **Denominador** | 2.469 (universo do painel — âncora §0) |
| **Sobreposição** | distribuição de domicílios por **nº de campanhas recebidas** (média 4,23; máx. 15) |
| **Grão de cálculo** | domicílio (nº de campanhas por lar) → agregar em distribuição |
| **Tabela Gold** | `bridge_household_campaign` (grão domicílio×campanha, a Silver `campaigns` promovida) + atributo `n_campaigns_exposed` por domicílio em `dim_household` |
| **Asset check** | `participation_coverage` — distintos expostos = 1.559; `SUM(n_campaigns_exposed)` sobre domicílios = 6.589 |

- **Uso analítico:** cruzar `n_campaigns_exposed` com segmento RFM (§5) responde "a quem o marketing estava falando?" — ex.: os Campeões receberam mais campanhas? Isto é **descritivo** (quem foi alvo), não um teste de efeito.
- **Limitações explícitas:**
  - **Viés de seleção de público:** se domicílios de maior valor receberam mais campanhas, qualquer comparação "expostos vs. não-expostos" confunde o efeito da campanha com o fato de já serem melhores clientes. Registrar isto sempre que cruzar exposição com receita/RFM.
  - **36,9% do painel nunca foi alvo** — esse grupo **não** é um grupo de controle válido (não foi aleatorizado; ver §8.6).

---

## 8.4 Resgate por campanha e por tipo (A/B/C) — **FACTUAL ✅**

**Definição (1 frase):** volume e alcance de resgates, agregados por campanha e por tipo de campanha.

| Campo | Especificação |
|---|---|
| **Métricas** | `n_redemption_events`, `n_households_redeemed` (distinto), `n_coupons_redeemed` (distinto), e a `redemption_rate_hh` da §8.2.a |
| **Numerador/Denominador** | contagens (volume); as **taxas** normalizam por expostos (§8.2) |
| **Grão de cálculo** | campanha **ou** `campaign_type` (A/B/C) |
| **Janela** | resgates 2017 (todos dentro) |
| **Filtros** | nenhum em `coupon_redemptions` (evento limpo) |
| **Tabela Gold** | `fct_coupon_redemption` (grão 1 evento: `household_id`, `coupon_upc`, `campaign_id`, `redemption_date`, `campaign_type` via join) → agregada em `agg_coupon_redemption` (grão campanha ou tipo) |
| **Asset check** | `redemption_event_count` — `fct_coupon_redemption` tem exatamente **2.102** linhas; distintos de domicílio = 410, de cupom = 491 |

- **Por que normalizar por tipo com cuidado:** cada tipo (A/B/C) cobre nº diferente de campanhas e de domicílios. "Tipo B teve mais resgates" pode só refletir que o Tipo B foi enviado a mais gente. **Sempre reportar a taxa (resgate ÷ expostos), não só o volume bruto.**
- **Limitações explícitas:**
  - **A/B/C são rótulos opacos** (mecânica não documentada) — descrever, não teorizar sobre "por que o tipo X converte mais".
  - Volume de eventos é dominado por poucos domicílios (410 lares, ~5 resgates cada) — **cauda curta e rara**; média por domicílio engana, reportar também nº de domicílios.

---

## 8.5 Receita "influenciada" por campanha — **ESTIMATIVA FRÁGIL ⚠️ — recomendo NÃO implementar na v1**

**Minha recomendação profissional: os dados NÃO suportam um número honesto de "receita de campanha". Não produzir um headline de receita atribuída.** Abaixo explico por quê, e ofereço, no máximo, **uma** métrica *descritiva/associativa* fortemente rotulada para quem insistir — nunca um KPI.

### 8.5.1 Por que a estimativa "produtos elegíveis × domicílios expostos × janela" é indefensável como headline

A tentação: para a campanha C, somar `sales_value` das transações onde `household_id ∈ expostos(C)` **e** `product_id ∈ elegíveis(C)` **e** `timestamp ∈ [start_date, end_date]`. Os problemas, em ordem de gravidade:

1. **Não é causal e não há contrafactual.** O lar compraria pão de qualquer forma. Sem grupo de controle, isto mede "receita que ocorreu perto da campanha", não "receita gerada pela campanha". Chamá-la de "influenciada" já é meio-caminho para a mentira.
2. **O cupom aplicado é desconhecido** (§8.0, verdade 3): `transactions` não tem `coupon_upc`, então nem se sabe se a venda do produto elegível envolveu o cupom. A "elegibilidade" é só "o produto estava na lista da campanha".
3. **Fan-out entre campanhas** (§8.0.2): 151 cupons em >1 campanha e produtos repetidos entre campanhas → **a mesma linha de venda entra na conta de várias campanhas**. Somar o total das 27 campanhas **superestima** grosseiramente. Não existe partição limpa da receita por campanha.
4. **Janelas truncadas** (§8.0.1): campanhas pré-2017 ou pós-jan/2018 têm período incompleto nos dados → comparação impossível ou enviesada.
5. **Viés de seleção de público** (§8.3): expostos podem já ser mais valiosos; a "receita influenciada" herda esse viés.

> Qualquer um desses pontos já bastaria para não cravar o número. Os cinco juntos tornam um headline de "receita de campanha" **irresponsável**. Um analista júnior que entrega "a campanha 18 gerou US$ X" está, na prática, inventando — sem perceber.

### 8.5.2 A ÚNICA forma descritiva aceitável (opcional, rotulada como associação, não atribuição)

Se o usuário quiser **alguma** cifra ligada a resgate, a menos enganosa é a **receita das cestas em que houve resgate** — associação por domicílio e dia, sem reivindicar causa:

| Campo | Especificação |
|---|---|
| **Definição** | receita das cestas feitas por um domicílio **no dia em que ele resgatou** um cupom |
| **Numerador** | `SUM(fct_basket.basket_revenue)` das cestas onde `(household_id, DATE(transaction_timestamp))` casa com um `(household_id, redemption_date)` de `coupon_redemptions` |
| **Denominador** | — (é um total descritivo; pode-se reportar como % da receita observada total, com ressalva) |
| **Grão de cálculo** | cesta (casada ao evento de resgate por domicílio×dia) |
| **Janela / data-ref** | 2017 (resgates dentro da janela) |
| **Tabela Gold candidata** | visão derivada de `fct_basket` × `fct_coupon_redemption` por `(household_id, data)` — **não** materializar como "receita de campanha" |
| **Asset check** | `redemption_basket_match_bounds` — receita casada ≤ receita observada total (US$ 4.596.039,58); nº de cestas casadas documentado |

- **Ressalvas que DEVEM acompanhar o número, sempre:**
  - É **associação por coincidência de dia**, não atribuição: a cesta inteira (não só o item do cupom) é contada, e ela existiria sem o cupom.
  - **Resgate day-grain** pode casar com >1 cesta do mesmo dia → definir explicitamente (ex.: casar todas as cestas do dia) e aceitar o ruído.
  - **Base minúscula** (410 domicílios) → não extrapolar para o painel.
  - **Nunca** rotular como "receita gerada/influenciada pela campanha". Rótulo honesto: *"receita observada em cestas coincidentes com resgate (associativo)"*.

---

## 8.6 Pré/pós-campanha — **EXPLORATÓRIO ⚠️ — adiar; só com aviso causal forte**

**Definição (1 frase):** comparar o gasto dos domicílios expostos **antes** vs. **durante/depois** da janela da campanha.

**Veredito: não é um KPI; na melhor hipótese é um gráfico didático com advertência. Recomendo adiar para depois dos fundamentos de campanha estarem validados.**

| Campo | Especificação (se feito) |
|---|---|
| **Definição** | para expostos à campanha C: `SUM(sales_value)` ou ticket médio num período **antes** de `start_date` vs. período **durante/depois** |
| **Grão de cálculo** | domicílio × período (pré/pós) |
| **Data de referência** | `start_date`/`end_date` da campanha (de `campaign_descriptions`), **nunca** a data atual |
| **Filtros** | só campanhas com janela pré **e** pós **inteiramente dentro** de 2017-01-01 → 2018-01-01 (exclui as truncadas — §8.0.1) |
| **Tabela Gold** | nenhuma dedicada na v1; derivável de `fct_basket` + `dim_campaign` se aprovado |

- **Por que é perigoso (os confundidores que impedem leitura causal):**
  - **Sem grupo de controle aleatorizado.** Os 36,9% não-expostos **não** são controle válido (seleção de público — §8.3).
  - **Sazonalidade:** campanhas coincidem com datas comerciais; o "pós" pode subir por feriado, não por campanha.
  - **Regressão à média / seleção:** se a campanha mirou quem comprava muito, o "pós" tende a cair naturalmente (e vice-versa).
  - **Truncamento de janela** elimina várias das 27 campanhas.
  - **Múltiplas campanhas simultâneas** por domicílio (4,23 em média) → impossível isolar o efeito de uma.
- **Se mesmo assim for feito:** rotular como **"comparação observacional, sem controle, sem reivindicação causal"**; nunca a frase "a campanha aumentou as vendas em X%".

---

## 8.7 Resumo da seção — o que implementar e o que evitar (para aprovação)

| # | Métrica | Classe | Tabela Gold | Recomendação |
|---|---|---|---|---|
| 8.1 | Alcance por campanha | **Factual ✅** | `agg_campaign_performance` | **Implementar 1º** — base segura |
| 8.3 | Participação / cobertura / sobreposição | **Factual ✅** | `bridge_household_campaign` + `dim_household.n_campaigns_exposed` | **Implementar 1º** |
| 8.4 | Resgate por campanha e tipo | **Factual ✅** | `fct_coupon_redemption` → `agg_coupon_redemption` | **Implementar 2º** |
| 8.2 | Taxa de resgate (resposta) | **Factual ✅** (denominador = expostos ou oferta, nunca "cupons enviados") | `agg_campaign_performance` | **Implementar 2º** (depende de 8.1 e 8.4) |
| 8.5 | Receita "influenciada" | **Estimativa frágil ⚠️** | — (no máximo visão associativa rotulada) | **NÃO implementar como KPI**; se exigido, só a versão associativa §8.5.2, rotulada |
| 8.6 | Pré/pós-campanha | **Exploratório ⚠️** | — | **Adiar**; só didático, com advertência causal |

**Ordem recomendada de construção:**
1. `bridge_household_campaign` + `dim_campaign` (fundação atemporal: quem recebeu o quê; metadados das 27 campanhas).
2. `agg_campaign_performance` (grão campanha: alcance §8.1 + taxas de resgate §8.2).
3. `fct_coupon_redemption` + `agg_coupon_redemption` (grão evento → tipo: §8.4).
4. Atributo `n_campaigns_exposed` em `dim_household` (habilita cruzar exposição × RFM — descritivo).
5. **Parar aqui na v1.** Receita influenciada (§8.5) e pré/pós (§8.6) só após decisão explícita do usuário, cientes das ressalvas.

**Princípio da seção:** entregar o que é **factual** (alcance, participação, resgate) com confiança total; tratar o que é **estimado** (receita influenciada, pré/pós) como território que os dados não sustentam para afirmação causal. É mais valioso um dashboard honesto que diz "estes lares foram alvo e estes resgataram" do que um número bonito de "ROI de campanha" que não se sustenta.

### Mentoria rápida (fecho da §8)
1. **Problema de negócio:** "a quem o marketing falou, e quem respondeu?" — não "quanto o marketing fez de caixa" (isto os dados não respondem honestamente).
2. **Conceito de Marketing Analytics:** o funil aqui só tem dois degraus **mensuráveis** — **exposição** (`campaigns`) e **resgate** (`coupon_redemptions`). Impressão, abertura, clique e **conversão causal** não existem nestes dados (se simulados, rotular como simulados).
3. **Como os dados são usados:** `campaigns` dá o denominador (expostos), `coupon_redemptions` dá o numerador (resgataram), `campaign_descriptions` dá tipo/janela, `coupons` dá elegibilidade (para contexto, nunca para somar receita).
4. **Por que estas definições:** taxa no grão de **domicílio/oferta** (não de evento) evita taxas > 100%; receita **nunca** somada após join com campanha/cupom (fan-out §8.0.2); "influenciada" rebaixada a associação porque falta `coupon_upc` e grupo de controle.
5. **Erro júnior a evitar:** (a) somar alcance das 27 campanhas e dizer "6.589 domicílios"; (b) dividir 2.102 eventos por 1.559 lares e chamar de "taxa"; (c) somar `coupon_disc` como "valor resgatado da campanha"; (d) dizer "a campanha gerou X de receita"; (e) ler pré/pós como efeito causal.
6. **Como validar (sanity checks):** exposições = 6.589; expostos distintos = 1.559 (63,1%); campanhas = 27; resgates = 2.102; resgatadores = 410 (26,3% dos expostos); cupons resgatados = 491; toda taxa ∈ [0,1]; numerador de resgate ⊆ expostos; receita associativa ≤ 4.596.039,58. Qualquer "receita de campanha" somada entre campanhas que ultrapasse a receita observada total é prova de fan-out.
