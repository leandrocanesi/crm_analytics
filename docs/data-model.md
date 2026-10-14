# Modelo de Dados — The Complete Journey (84.51°)

> Baseado em **inspeção real** dos arquivos em `data/raw/completejourney/` (2026-10-14). Schema 84.51° "tidy". Ver `data-dictionary.md` para campos/tipos e `PROVENANCE.md` para origem.
> Período coberto pelas transações: **2017-01-01 a 2018-01-01** (semanas 1–53). Data de referência para recência = **máxima data observada**, nunca a data atual.

## 1. Entidades e granularidade (resumo)

| Entidade | Grão (1 linha =) | Linhas | PK |
|---|---|---|---|
| `transactions` | 1 produto em 1 cesta (item de linha de venda) | 1.469.307 | `(basket_id, product_id)` |
| `promotions` | 1 produto × loja × semana × display × encarte | 20.940.529 | grão composto (5 col.) |
| `products` | 1 produto | 92.331 | `product_id` |
| `coupons` | 1 cupom × produto × campanha (após dedupe) | 116.204 | `(coupon_upc, product_id, campaign_id)` |
| `coupon_redemptions` | 1 resgate de cupom por domicílio | 2.102 | sem PK natural limpa (evento) |
| `campaigns` | 1 domicílio exposto a 1 campanha | 6.589 | `(campaign_id, household_id)` |
| `campaign_descriptions` | 1 campanha | 27 | `campaign_id` |
| `demographics` | 1 domicílio | 801 | `household_id` |

Dimensões implícitas (sem tabela própria): **loja** (`store_id`, 457 em transactions) e **tempo** (`week` 1–53 / `transaction_timestamp`). Serão materializadas como dimensões derivadas em Gold.

## 2. Diagrama relacional (texto)

```
                         ┌───────────────────────┐
                         │ campaign_descriptions │  (27)  PK campaign_id
                         │  type, start, end     │
                         └───────────┬───────────┘
                                     │ 1
                      ┌──────────────┼───────────────┐
                    N │            N │             N  │
              ┌───────┴──────┐ ┌─────┴──────┐  ┌──────┴──────────────┐
              │  campaigns   │ │  coupons   │  │ coupon_redemptions  │
              │ (6.589)      │ │ (116.204)  │  │ (2.102)             │
              │ campaign_id  │ │ coupon_upc │  │ household_id        │
              │ household_id │ │ product_id │  │ coupon_upc          │
              └──────┬───────┘ └─────┬──────┘  │ campaign_id         │
                     │ N             │ N       │ redemption_date     │
                     │               │         └─────────┬───────────┘
      household_id   │               │ product_id        │ household_id / coupon_upc
                     │               │                   │
   ┌─────────────────┴──┐     ┌──────┴───────┐           │
   │   demographics     │     │  products    │◄──────────┘ (via coupon_upc→coupons→product)
   │   (801 de 2.469)   │     │  (92.331)    │
   │   PK household_id  │     │ PK product_id│
   └─────────┬──────────┘     └──────┬───────┘
             │ 0..1                  │ 1
             │ household_id          │ product_id
             │                 ┌─────┴────────────────────────────┐
             │   household_id  │          transactions            │ N
             └────────────────►│  (1.469.307)  ★ FATO DE RECEITA  │◄───┐
                               │  PK (basket_id, product_id)      │    │ product_id + store_id + week
                               │  sales_value = RECEITA OBSERVADA │    │ (contexto, NÃO join 1:1)
                               └──────────────────────────────────┘    │
                                                              ┌────────┴─────────┐
                                                              │   promotions     │
                                                              │  (20.940.529)    │
                                                              │ product/store/wk │
                                                              └──────────────────┘
```

Legenda: `★` = tabela-fato. Linhas `◄──` tracejadas conceituais (promotions/coupons) **não** são joins linha-a-linha com a fato — são contexto que fan-out (ver §4).

## 3. Fonte única de verdade da RECEITA

**Receita observada = `SUM(transactions.sales_value)` no grão item-de-linha.** Total do período = **US$ 4.596.039,58**.

Por quê esta coluna e não outra:
- `sales_value` = "valor em dólares que o varejista recebe pela venda" — é o dinheiro efetivamente realizado, **já líquido** do desconto de fidelidade (`retail_disc`) e do cupom aplicado no caixa. É a definição de receita observada do varejista.
- **Não** reconstruir receita somando descontos (`sales_value + retail_disc + coupon_disc`): isso dá **preço de prateleira/list value**, uma métrica diferente (útil para medir desconto concedido, não receita).
- Nesta release os descontos são **magnitudes positivas** (na dunnhumby crua eram negativos) — não inverter sinais por hábito.

Métricas derivadas permitidas a partir da fato (mesmo grão, sem novos joins de receita):
- `list_value = sales_value + retail_disc` (preço cheio aproximado)
- `total_discount = retail_disc + coupon_disc + coupon_match_disc`
- `manufacturer_funded = coupon_disc`; `retailer_funded_discount = retail_disc + coupon_match_disc`

## 4. Riscos de dupla contagem (fan-out) — regra de ouro

**Receita só se calcula a partir de `transactions`. Nunca somar `sales_value` depois de juntar a uma tabela de cardinalidade maior.**

| Join ingênuo | O que acontece | Regra segura |
|---|---|---|
| `transactions × promotions` em `(product_id, store_id, week)` | Explode: há múltiplas linhas de promoção (display + encarte) por produto/loja/semana (12.785 dups nesse grão). Cada item de venda vira N linhas → receita inflada. | Reduzir promotions a **1 linha por `(product_id, store_id, week)`** com flags (`on_display`, `in_mailer`) **antes** de juntar; ou usar `EXISTS`. Juntar só para enriquecer, agregar receita **antes**. |
| `transactions × coupons` em `product_id` | Um produto aparece em vários cupons/campanhas (41.857 produtos, 116k linhas, com duplicatas). Cada venda do produto se multiplica. | Nunca juntar a fato por `product_id` para somar receita. Usar coupons só para montar a lista de elegibilidade por campanha. |
| `transactions × campaigns` em `household_id` | Domicílio tem em média 4,23 campanhas. Cada linha de venda × nº de campanhas → receita × ~4. | Para "receita de domicílios de uma campanha", filtrar `household_id IN (público da campanha)` e somar a fato **sem** juntar a tabela ponte linha a linha. |
| `transactions × coupon_redemptions` | Não há chave de linha; join por household/data duplica. | Resgate é um **fato separado** (contagem de eventos), não um multiplicador de receita. |

**Teste de validação (asset check sugerido):** qualquer visão Gold que exponha receita deve reproduzir **US$ 4.596.039,58** no período completo. Divergência = fan-out.

**Limitação de atribuição:** `transactions` tem `coupon_disc>0` mas **não** o `coupon_upc` aplicado. Atribuir receita a um cupom/campanha específico é **estimativa** (ex.: via produtos elegíveis + janela da campanha), nunca fato — rotular como derivado/aproximado e jamais afirmar causalidade sem grupo de controle.

## 5. Estratégia de camadas Bronze → Silver → Gold

### Bronze (ingestão fiel + metadados técnicos) — *implementação é do analytics-engineer*
- Converter cada `.rds`/`.rda` em Parquet **1:1**, sem limpeza semântica. `.rda` com objeto nomeado → extrair o dataframe; `.rds` → objeto único.
- Preservar nomes/tipos de origem (IDs como string). Adicionar metadados: `_source_file`, `_ingested_at`, `_row_count`, hash do arquivo (cruzar com `SHA256SUMS.txt`).
- Tabelas pesadas (`transactions` 1,47M, `promotions` 20,9M) → Parquet particionado por `week` para leitura eficiente.
- Idempotente: reexecutar com o mesmo input produz o mesmo output (mesmo hash de conteúdo).

### Silver (tipagem, limpeza, integridade) — **IMPLEMENTADA** (2026-10-14)
Materializada em `data/processed/silver/<tabela>/` (mesmo particionamento por
`week` da Bronze). Preserva **todas as linhas** (marca, não remove) exceto o
dedupe exato de `coupons`. Colunas de auditoria Bronze **não** são propagadas;
derivadas são rotuladas (`is_*`, `has_demographics`). Código:
`pipelines/crm_pipelines/silver.py` + `silver_config.py`.
- **Tipos:** IDs → string; monetários (`sales_value`, `retail_disc`,
  `coupon_disc`, `coupon_match_disc`) → **`DECIMAL(12,2)`** (todos os valores têm
  exatamente 2 casas; o total de receita permanece **US$ 4.596.039,58** exato —
  validado pelo check `revenue_preserved`); `transaction_timestamp` → timestamp;
  `week` → integer; categóricos validados contra o domínio observado (check
  `categorical_domains_valid`).
- **Decisões de limpeza aplicadas (aprovadas pelo usuário):**
  - `coupons`: **dedupe exato** por `(coupon_upc, product_id, campaign_id)` →
    116.204 → **111.332** linhas (remove as 4.872 duplicatas idênticas).
  - `products` órfãos: 17 `product_id` de transactions sem cadastro → flag
    `is_orphan_product` em `silver.transactions` (4.836 linhas). A linha de venda
    e sua receita são **mantidas**; nenhum membro sintético é criado (evita
    inventar `brand`/`department`). Gold resolve o desconhecido no join.
  - `transactions`: flags booleanas (não remove) — `is_zero_qty` (8.869),
    `is_free_item` (11.226), `is_weighted` (13.494, itens por peso). Política de
    inclusão por métrica fica no Gold.
  - `demographics`: `home_ownership` (233) e `marital_status` (137) nulos →
    `'Unknown'`; coluna `has_demographics` (nesta tabela sempre `TRUE`). **Viés
    de cobertura: 801 de 2.469 domicílios (32,4%)** — a flag de cobertura sobre o
    universo completo de domicílios é materializada no Gold (`dim_household`).
- **Integridade referencial:** asset checks `fk_*` de severidade **WARN** que
  **registram** a contagem de órfãos como metadado e **não** quebram o pipeline
  (órfãos conhecidos: `transactions.product_id` 17, `coupons.product_id` 6).
  `household_id` não tem tabela-mestre (2.469 domicílios sem dimensão própria) →
  sem check de FK; `demographics` é cobertura parcial por design, não violação.
- **Chaves duplicadas:** check `primary_key_unique` (ERROR) nas PKs naturais
  limpas (transactions, products, coupons, campaigns, campaign_descriptions,
  demographics). `coupon_redemptions` é evento sem PK natural; `promotions` tem
  grão composto de 5 colunas (unicidade validada na inspeção Bronze).

### Gold (visões analíticas prontas para a API, grão explícito)
Cada tabela/visão declara seu grão. Receita sempre pré-agregada da fato. Candidatas:
- `fct_transaction_line` — a fato limpa (grão item-de-linha) + colunas derivadas de receita/desconto.
- `fct_basket` — grão **1 cesta**: `basket_id`, household, store, timestamp, `n_items`, `basket_revenue=SUM(sales_value)`. Base de ticket médio.
- `agg_household_rfm` — grão **1 domicílio**: recência (vs. data máx. observada), frequência (nº de cestas), valor monetário (SUM sales_value). **Definir com `analytics-mentor` antes de implementar.**
- `agg_weekly_revenue` — grão `week` (× store opcional): receita, cestas, domicílios ativos.
- `dim_product`, `dim_household` (demografia + flag de cobertura), `dim_store`, `dim_campaign`.
- `bridge_household_campaign`, `fct_coupon_redemption` (grão evento) — para análise de campanha/cupom **sem** contaminar receita.

Tudo materializado como snapshot DuckDB publicado de forma controlada (ver `docs/snapshots.md`); Dagster é o único escritor, API só lê snapshot read-only.

## 6. Mentoria rápida
1. **Negócio:** separar "quanto o cliente comprou" (fato) de "a que ele foi exposto" (campanha/promo) evita confundir exposição com resultado.
2. **Conceito CRM:** a fato de item-de-linha sobe para cesta → domicílio (RFM) → coorte. O grão nunca "desce"; só agrega.
3. **Erro júnior:** achar que mais joins = mais informação. Em tabelas-fato, join errado = receita inflada. Agregue antes de enriquecer.
4. **Causalidade:** campanhas não têm grupo de controle aqui. "Comprou mais depois da campanha" ≠ "a campanha causou". Sempre qualificar.
5. **Validação-âncora:** receita total = US$ 4.596.039,58; qualquer número que a contradiga está errado por construção.
