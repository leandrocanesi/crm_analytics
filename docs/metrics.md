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
