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

### Silver (tipagem, limpeza, integridade) — decisões a documentar
- **Tipos:** IDs → string; monetários → decimal/float; datas → date/timestamp; categóricos → category com domínio validado contra os valores observados (ver dicionário).
- **Decisões de limpeza (candidatas, discutir antes de cravar):**
  - `coupons`: **deduplicar** (4.872 linhas idênticas; 10.942 dups em `(coupon_upc, product_id)`).
  - `products`: 17 `product_id` de transactions ausentes → criar membro "produto desconhecido" ou flag de órfão; **não descartar a receita** da linha.
  - `transactions`: marcar (não remover) linhas atípicas — `quantity=0` (8.869), `sales_value=0` (11.226, itens grátis/promo), `quantity>1000` (13.494, itens por peso). Decidir política de inclusão por métrica, não globalmente.
  - `demographics`: manter nulos reais (`home_ownership` 29%, `marital_status` 17%) como categoria "Unknown"; **sinalizar cobertura de 32%** para toda segmentação (viés).
  - Normalizar `week` ↔ `transaction_timestamp` e padronizar fuso (timestamps são naïve, grão de segundo).
- **Integridade referencial:** validar FKs (`product_id`, `household_id`, `campaign_id`, `coupon_upc`) via asset checks; registrar órfãos em vez de falhar silenciosamente.
- Rotular explicitamente colunas **derivadas** (ex. `list_value`) vs originais.

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
