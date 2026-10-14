# pipelines — Dagster (Customer Intelligence Lab)

Orquestração de dados do laboratório. **Escopo atual: camadas Bronze e Silver.**
Bronze = ingestão fiel 1:1 dos arquivos `.rds`/`.rda` da dunnhumby "The Complete
Journey" para Parquet, com metadados técnicos e asset checks. Silver = tipagem,
limpeza, padronização e integridade sobre o Parquet Bronze. Gold ainda **não**
implementada.

O Dagster é o **único escritor** do DuckDB/artefatos de dados (CLAUDE.md regra 6).
Bronze grava em `data/processed/bronze/`, Silver em `data/processed/silver/`.
Nenhum snapshot DuckDB é publicado nesta fase.

## Layout
```
pipelines/
  crm_pipelines/
    __init__.py       # Definitions (code location): assets Bronze + Silver
    config.py         # caminhos, TableSpec (Bronze), contagens, âncora de receita
    readers.py        # leitura .rds/.rda (pyreadr) + hashing
    bronze.py         # fábrica de assets Bronze + asset checks
    silver_config.py  # SilverSpec (SQL, domínios, FKs, PKs) por tabela
    silver.py         # fábrica de assets Silver (DuckDB) + asset checks
  tests/              # pytest (test_bronze, test_silver)
  pyproject.toml      # deps, ruff, pytest, [tool.dagster]
  requirements.txt    # ambiente congelado (pip freeze)
```

## Setup (Windows, Python 3.13)
```bash
cd pipelines
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pip install -e .   # registra o pacote crm_pipelines
```

## Rodar o pipeline Bronze

Materializar **todas** as tabelas Bronze (roda os asset checks junto):
```bash
cd pipelines
.venv/Scripts/dagster.exe asset materialize -m crm_pipelines --select "*"
```

Materializar **uma** tabela (ex. só transactions):
```bash
.venv/Scripts/dagster.exe asset materialize -m crm_pipelines --select "transactions"
```

UI interativa (materializar e inspecionar metadados/checks no navegador):
```bash
.venv/Scripts/dagster.exe dev -m crm_pipelines    # http://localhost:3000
```

## Rodar a camada Silver

Depende da Bronze já materializada (lê `data/processed/bronze/`). Dependência
bronze → silver é explícita em cada asset. Materializar toda a Silver:
```bash
cd pipelines
.venv/Scripts/dagster.exe asset materialize -m crm_pipelines --select "group:silver"
```
Uma tabela (note o prefixo de chave `silver/`):
```bash
.venv/Scripts/dagster.exe asset materialize -m crm_pipelines --select "silver/transactions"
```

## Verificações
```bash
cd pipelines
.venv/Scripts/python.exe -m ruff check crm_pipelines tests
.venv/Scripts/python.exe -m pytest        # usa só tabelas pequenas (rápido)
```

## Saída
**Bronze** — `data/processed/bronze/<tabela>/`. `transactions`/`promotions`
particionadas por `week`; demais em arquivo único. Toda tabela ganha colunas de
auditoria: `_source_file`, `_ingested_at`, `_row_count`, `_source_sha256`.

**Silver** — `data/processed/silver/<tabela>/`, mesmo layout de particionamento.
Preserva **todas as linhas** (marca, não remove) exceto o dedupe exato de
`coupons`. Colunas de auditoria Bronze **não** são propagadas (Silver é a camada
limpa); colunas derivadas são rotuladas (`is_*`, `has_demographics`).

Decisões aplicadas na Silver:
- Monetários (`sales_value`, `retail_disc`, `coupon_disc`, `coupon_match_disc`)
  → `DECIMAL(12,2)` — preserva o total de receita **US$ 4.596.039,58** exato.
- `coupons`: dedupe exato por `(coupon_upc, product_id, campaign_id)` →
  116.204 → **111.332** linhas (remove 4.872 duplicatas idênticas).
- `transactions`: flags `is_zero_qty` (8.869), `is_free_item` (11.226),
  `is_weighted` (13.494, itens por peso), `is_orphan_product` (4.836 linhas /
  17 produtos sem cadastro). **Nenhuma linha removida** — política de inclusão
  por métrica fica no Gold.
- `demographics`: `home_ownership` (233) e `marital_status` (137) nulos →
  `'Unknown'`; coluna `has_demographics`. **Viés de cobertura: 801 de 2.469
  domicílios (32,4%)** — a flag sobre o universo completo é do Gold
  (`dim_household`).

## Asset checks — Bronze (por tabela)
- `row_count_matches_expected` — nº de linhas == esperado (dicionário de dados).
- `schema_not_empty` — ao menos uma coluna de origem.
- `source_sha256_matches` — hash do arquivo bruto confere com `SHA256SUMS.txt`.
- `revenue_anchor` (só `transactions`) — `SUM(sales_value) ≈ US$ 4.596.039,58`.

## Asset checks — Silver (por tabela, conforme aplicável)
- `row_count_matches_expected` (ERROR) — contagem esperada (coupons = 111.332).
- `key_columns_not_null` (ERROR) — sem nulos nas colunas-chave após tratamento.
- `primary_key_unique` (ERROR) — PK sem duplicatas (onde há PK natural limpa).
- `categorical_domains_valid` (ERROR) — categóricos dentro do domínio observado.
- `revenue_preserved` (ERROR, só `transactions`) — `SUM(sales_value)` segue
  em **US$ 4.596.039,58** (tipagem DECIMAL não altera o total).
- `monetary_values_valid` (ERROR, só `transactions`) — sem negativos / absurdos.
- `fk_*` (**WARN**) — integridade referencial. **Registra** a contagem de órfãos
  como metadado e **não quebra** o pipeline (órfãos conhecidos são esperados:
  `transactions.product_id` 17 órfãos, `coupons.product_id` 6 órfãos).

## Nota de reprodutibilidade
A coluna `_ingested_at` é carimbo de auditoria (hora de execução) e varia entre
execuções. A garantia de reprodutibilidade é sobre o **conteúdo de negócio**: o
metadado `content_sha256` (hash das colunas de origem, sem auditoria) é idêntico
a cada reexecução com o mesmo input. A gravação é idempotente — a pasta de saída
é recriada do zero a cada run (sem acúmulo de arquivos).
