# pipelines — Dagster (Customer Intelligence Lab)

Orquestração de dados do laboratório. **Escopo atual: camada Bronze** (ingestão
fiel 1:1 dos arquivos `.rds`/`.rda` da dunnhumby "The Complete Journey" para
Parquet, com metadados técnicos e asset checks). Silver e Gold ainda **não**
implementadas.

O Dagster é o **único escritor** do DuckDB/artefatos de dados (CLAUDE.md regra 6).
A Bronze grava Parquet em `data/processed/bronze/`. Nenhum snapshot é publicado
nesta fase.

## Layout
```
pipelines/
  crm_pipelines/
    __init__.py     # Definitions (code location): 1 asset Bronze por tabela
    config.py       # caminhos, TableSpec, contagens esperadas, âncora de receita
    readers.py      # leitura .rds/.rda (pyreadr) + hashing
    bronze.py       # fábrica de assets Bronze + asset checks
  tests/            # pytest (tabelas pequenas)
  pyproject.toml    # deps, ruff, pytest, [tool.dagster]
  requirements.txt  # ambiente congelado (pip freeze)
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

## Verificações
```bash
cd pipelines
.venv/Scripts/python.exe -m ruff check crm_pipelines tests
.venv/Scripts/python.exe -m pytest        # usa só tabelas pequenas (rápido)
```

## Saída
`data/processed/bronze/<tabela>/` em Parquet. `transactions` e `promotions` são
particionadas por `week` (`week=1/…`, `week=2/…`). As demais são arquivo único.
Toda tabela ganha colunas de auditoria: `_source_file`, `_ingested_at`,
`_row_count`, `_source_sha256`.

## Asset checks (por tabela)
- `row_count_matches_expected` — nº de linhas == esperado (dicionário de dados).
- `schema_not_empty` — ao menos uma coluna de origem.
- `source_sha256_matches` — hash do arquivo bruto confere com `SHA256SUMS.txt`.
- `revenue_anchor` (só `transactions`) — `SUM(sales_value) ≈ US$ 4.596.039,58`.

## Nota de reprodutibilidade
A coluna `_ingested_at` é carimbo de auditoria (hora de execução) e varia entre
execuções. A garantia de reprodutibilidade é sobre o **conteúdo de negócio**: o
metadado `content_sha256` (hash das colunas de origem, sem auditoria) é idêntico
a cada reexecução com o mesmo input. A gravação é idempotente — a pasta de saída
é recriada do zero a cada run (sem acúmulo de arquivos).
