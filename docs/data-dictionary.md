# Dicionário de Dados — The Complete Journey (84.51°)

> Fonte real: pacote R `completejourney` (84.51° / dunnhumby US). Confirmado por **inspeção** dos arquivos `.rds`/`.rda` em `data/raw/completejourney/` em 2026-10-14 — nada aqui é presumido.
> Esta é a release **84.51° "tidy"** (colunas em inglês, ~2.469 domicílios, ~1 ano), **não** a release crua original da dunnhumby (`HOUSEHOLD_KEY`, `DAY`, 2 anos). Ver `data/raw/completejourney/PROVENANCE.md`.

## Convenções
- **Tipo real** = dtype observado ao ler com `pyreadr` em pandas. IDs chegam como **string** (`str`) na origem R — manter como texto (são códigos, não números a somar).
- **Dado real** = original do estudo 84.51°. Nenhum campo abaixo é derivado ou sintético; derivações/sintéticos entram só nas camadas Silver/Gold e serão rotulados lá.
- **Domicílio (`household_id`) ≠ indivíduo.** É a unidade de análise (uma conta de fidelidade / lar), nunca uma pessoa identificada.
- **Período do dataset**: transações de **2017-01-01 a 2018-01-01** (semanas 1–53 de 2017). **Nunca** usar a data atual como referência de recência — usar a data máxima observada (`2018-01-01`, fim da semana 53).

---

## 1. `transactions` (transactions.rds)
**Grão:** 1 linha = **1 produto dentro de 1 cesta (basket)** — isto é, um item de linha de venda. Confirmado: `(basket_id, product_id)` é **único** (0 duplicatas em 1.469.307 linhas). `basket_id` mapeia para exatamente 1 domicílio, 1 loja e 1 timestamp.
**Linhas:** 1.469.307 · **Nulos:** nenhuma coluna tem nulos.
**Fonte única de verdade da RECEITA OBSERVADA:** `SUM(sales_value)` neste grão. Total no período = **US$ 4.596.039,58**.

| Coluna | Tipo real | Descrição | Nulos | Exemplo |
|---|---|---|---|---|
| `household_id` | str | Domicílio (conta de fidelidade) que fez a compra. FK → demographics (parcial). | 0 | `900` |
| `store_id` | str | Loja onde ocorreu a transação. 457 lojas distintas. | 0 | `330` |
| `basket_id` | str | Identificador da cesta/compra (um "ticket"). 155.848 cestas distintas. | 0 | `31198570044` |
| `product_id` | str | Produto vendido. FK → products. 68.509 produtos distintos transacionados. | 0 | `1095275` |
| `quantity` | float64 | Quantidade do produto na linha. Pode ser 0 (ver QA) e assume valores grandes para itens por peso. Faixa 0–89.638. | 0 | `1.0` |
| `sales_value` | float64 | **Receita observada**: valor em dólares que o varejista recebe pela venda desta linha (líquido de desconto de fidelidade e do cupom aplicado no caixa). Faixa 0–840. | 0 | `0.50` |
| `retail_disc` | float64 | Desconto (magnitude ≥ 0) aplicado pelo programa de fidelidade do varejista. Faixa 0–130,02. | 0 | `0.00` |
| `coupon_disc` | float64 | Desconto (magnitude ≥ 0) de cupom do **fabricante**. Faixa 0–55,93. 21.889 linhas > 0. | 0 | `0.0` |
| `coupon_match_disc` | float64 | Desconto (magnitude ≥ 0) do varejista ao **igualar** um cupom de fabricante. Faixa 0–7,7. 10.300 linhas > 0. | 0 | `0.0` |
| `week` | int32 | Semana do estudo (1–53). Derivável do timestamp, mas vem pronta na origem. | 0 | `1` |
| `transaction_timestamp` | datetime64[s] | Data/hora da transação (grão de segundo). 2017-01-01 → 2018-01-01. | 0 | `2017-01-01 11:53:26` |

**Chaves:** PK = `(basket_id, product_id)`. FK: `product_id`→`products`, `household_id`→`demographics` (só 801 de 2.469 têm demografia), `store_id`→`promotions.store_id` (dimensão implícita, sem tabela de lojas).
**Notas de sinal (importante):** nesta release os descontos são **magnitudes positivas** (na release crua da dunnhumby eram negativos). `sales_value` **já é líquido** — **não** somar os descontos de volta para obter "receita". `sales_value + retail_disc` ≈ preço de prateleira (list price), que é outra métrica.

---

## 2. `promotions` (promotions.rds)
**Grão:** 1 linha = **1 produto, em 1 loja, em 1 semana, em uma combinação de local de display e local de encarte**. `(product_id, store_id, week)` **não** é único (12.785 duplicatas) porque o mesmo produto pode estar em display **e** em encarte na mesma semana; o grão completo `(product_id, store_id, week, display_location, mailer_location)` tem 0 duplicatas totais.
**Linhas:** 20.940.529 (tabela mais pesada — é a vitrine de exposição/circular, não vendas).

| Coluna | Tipo real | Descrição | Nulos | Exemplo |
|---|---|---|---|---|
| `product_id` | str | Produto promovido. FK → products. 59.800 distintos. | 0 | `1000050` |
| `store_id` | str | Loja. 112 lojas (subconjunto das 457 de transactions). | 0 | `316` |
| `display_location` | category | Código do local de exposição em loja. Domínio: `0`(sem display),`1`–`7`,`9`,`A`. | 0 | `9` |
| `mailer_location` | category | Código do local no encarte/circular. Domínio: `0`(fora do encarte),`A`,`C`,`D`,`F`,`H`,`J`,`L`,`P`,`X`,`Z`. | 0 | `0` |
| `week` | int32 | Semana do estudo (1–53), alinhada a `transactions.week`. | 0 | `1` |

**Chaves:** sem PK natural de 1 coluna; grão composto acima. FK `product_id`→`products`, `store_id`/`week` ligam a `transactions` por **contexto** (não é join de linha 1:1).
**Uso:** indica **oportunidade de exposição** (produto estava em display/encarte), não que o domicílio viu ou comprou. Correlação ≠ causalidade em análises de "lift de promoção".

---

## 3. `products` (products.rda)
**Grão:** 1 linha = **1 produto**. `product_id` é PK (92.331 linhas, 92.331 únicos).
**Linhas:** 92.331.

| Coluna | Tipo real | Descrição | Nulos | Exemplo |
|---|---|---|---|---|
| `product_id` | str | **PK**. Identificador do produto. | 0 | `25671` |
| `manufacturer_id` | str | Código do fabricante (anônimo). 6.471 distintos. | 0 | `2` |
| `department` | str | Departamento (nível alto). 32 valores (ex. GROCERY, PASTRY). | 0 | `GROCERY` |
| `brand` | category | `National` (marca nacional) ou `Private` (marca própria). | 0 | `National` |
| `product_category` | str | Categoria/commodity (nível médio). 303 valores. | 540 (0,6%) | `FRZN ICE` |
| `product_type` | str | Subcategoria (nível fino). 2.378 valores. | 528 (0,6%) | `ICE - CRUSHED/CUBED` |
| `package_size` | str | Tamanho/embalagem como texto livre (ex. `22 LB`, `50 OZ`). | 30.586 (33,1%) | `22 LB` |

**Nota de integridade:** 17 `product_id` presentes em `transactions` **não** existem em `products` (produtos órfãos) — tratar em Silver (flag/quarentena, não descartar receita).

---

## 4. `coupons` (coupons.rda)
**Grão:** 1 linha = **1 associação cupom × produto × campanha** (quais produtos cada cupom cobre, em qual campanha).
**Linhas:** 116.204. **Atenção:** há **4.872 linhas totalmente duplicadas** e 10.942 duplicatas em `(coupon_upc, product_id)` → **deduplicar em Silver**. Um `coupon_upc` normalmente pertence a 1 campanha, mas 151 mapeiam para >1 (máx. 5).

| Coluna | Tipo real | Descrição | Nulos | Exemplo |
|---|---|---|---|---|
| `coupon_upc` | str | Identificador do cupom (UPC). 981 cupons distintos. | 0 | `10000085207` |
| `product_id` | str | Produto elegível ao cupom. FK → products. 41.857 distintos. | 0 | `9676830` |
| `campaign_id` | str | Campanha que distribuiu o cupom. FK → campaign_descriptions. | 0 | `26` |

**Chaves:** grão composto `(coupon_upc, product_id, campaign_id)` (após dedupe). FK `product_id`→`products`, `campaign_id`→`campaign_descriptions`.

---

## 5. `coupon_redemptions` (coupon_redemptions.rda)
**Grão:** 1 linha = **1 resgate** de um cupom por um domicílio em uma campanha, numa data.
**Linhas:** 2.102. Apenas 410 domicílios resgataram algo (evento raro).

| Coluna | Tipo real | Descrição | Nulos | Exemplo |
|---|---|---|---|---|
| `household_id` | str | Domicílio que resgatou. FK → campaigns (todos presentes). | 0 | `1029` |
| `coupon_upc` | str | Cupom resgatado. FK → coupons (subconjunto confirmado). 491 distintos. | 0 | `51380041013` |
| `campaign_id` | str | Campanha do resgate. FK → campaigns/campaign_descriptions. | 0 | `26` |
| `redemption_date` | date | Data do resgate (grão de dia, sem hora). 2017-01-01 → 2017-12-31. | 0 | `2017-01-01` |

**Limitação crítica:** **não** há ligação direta entre um resgate e a **linha de transação** correspondente. `transactions` registra `coupon_disc>0` mas **não** diz qual `coupon_upc`. Atribuir receita específica a um cupão é, portanto, **aproximação**, não fato — documentar em qualquer métrica.

---

## 6. `campaigns` (campaigns.rda)
**Grão:** 1 linha = **1 domicílio exposto a 1 campanha** (quem recebeu cada campanha).
**Linhas:** 6.589 (0 duplicatas). 1.559 domicílios distintos; em média 4,23 campanhas/domicílio (máx. 15).

| Coluna | Tipo real | Descrição | Nulos | Exemplo |
|---|---|---|---|---|
| `campaign_id` | str | Campanha. FK → campaign_descriptions. 27 distintas. | 0 | `1` |
| `household_id` | str | Domicílio-alvo. Todos existem em transactions. | 0 | `105` |

**Chaves:** PK = `(campaign_id, household_id)`. Tabela ponte N:N entre domicílios e campanhas.

---

## 7. `campaign_descriptions` (campaign_descriptions.rda)
**Grão:** 1 linha = **1 campanha** e seu período. `campaign_id` é PK (27 linhas, 27 únicos).
**Linhas:** 27.

| Coluna | Tipo real | Descrição | Nulos | Exemplo |
|---|---|---|---|---|
| `campaign_id` | str | **PK**. Identificador da campanha. | 0 | `1` |
| `campaign_type` | category | `Type A`, `Type B` ou `Type C` (natureza/mecânica da campanha). | 0 | `Type B` |
| `start_date` | date | Início da campanha. | 0 | `2017-03-03` |
| `end_date` | date | Fim da campanha. | 0 | `2017-04-09` |

**Nota temporal:** janela das campanhas (2016-11-14 → 2018-02-28) **excede** a janela de transações (2017). Algumas começam antes / terminam depois dos dados de venda — cuidado ao medir efeito pré/pós.

---

## 8. `demographics` (demographics.rda)
**Grão:** 1 linha = **1 domicílio** com atributos demográficos. `household_id` é PK (801 linhas, 801 únicos).
**Linhas:** 801. **Cobertura: apenas 801 de 2.469 domicílios (32,4%)** têm demografia — forte **viés de cobertura** para segmentação. Todos os 801 existem em transactions.

| Coluna | Tipo real | Descrição | Nulos | Exemplo |
|---|---|---|---|---|
| `household_id` | str | **PK**. Domicílio. | 0 | `1` |
| `age` | category | Faixa etária do chefe do domicílio. Domínio: `19-24`,`25-34`,`35-44`,`45-54`,`55-64`,`65+`. | 0 | `65+` |
| `income` | category | Faixa de renda. 12 faixas (`Under 15K` … `250K+`). | 0 | `35-49K` |
| `home_ownership` | category | Posse da moradia (ex. Homeowner, Renter). 4 valores. | 233 (29,1%) | `Homeowner` |
| `marital_status` | category | Estado civil (Married/Unmarried). | 137 (17,1%) | `Married` |
| `household_size` | category | Tamanho do domicílio (nº de pessoas). 5 faixas. | 0 | `2` |
| `household_comp` | category | Composição: `1/2 Adult(s) No Kids`, `1/2 Adult(s) Kids`. | 0 | `2 Adults No Kids` |
| `kids_count` | category | Nº de crianças: `0`,`1`,`2`,`3+`. | 0 | `0` |

**Lembrete:** atributos demográficos descrevem o **domicílio**, não um indivíduo. Usar sempre agregado.

---

## Mentoria rápida — por que isto importa
1. **Problema de negócio:** medir e explicar comportamento de compra (receita, frequência, cesta, resposta a campanha) para decisões de CRM/retenção.
2. **Conceito:** o item de linha de `transactions` é o átomo de toda métrica de receita; tudo o mais são **dimensões** (quem, o quê, onde, promovido como).
3. **Erro júnior clássico:** juntar `transactions` com `promotions`/`coupons`/`campaigns` e **somar `sales_value`** → infla a receita (fan-out). Ver `data-model.md`.
4. **Validação:** a receita total do período deve bater em **US$ 4.596.039,58** independentemente de quais dimensões forem anexadas. Se mudar ao adicionar um join, há dupla contagem.
