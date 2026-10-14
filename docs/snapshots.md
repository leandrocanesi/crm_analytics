# Snapshots DuckDB — publicação do artefato read-only da API

> Como o pipeline Dagster transforma as tabelas **Gold** (Parquet) no arquivo
> `.duckdb` **read-only** que a API FastAPI consome — com segurança de
> concorrência, validação-âncora antes de publicar e troca atômica compatível
> com Windows.

Implementação: `pipelines/crm_pipelines/snapshot.py` e `snapshot_config.py`.
Asset Dagster: `snapshot/published_snapshot` (grupo `snapshot`).

---

## 1. Por que um snapshot? (o problema de concorrência)

O DuckDB é um banco **embutido** (um arquivo, sem servidor). Dois processos não
podem abrir o **mesmo** arquivo para escrita ao mesmo tempo sem risco de corromper
ou travar. No nosso sistema há dois atores:

- **Dagster** — materializa Bronze → Silver → Gold e precisa **escrever**.
- **API FastAPI** — responde requisições e só precisa **ler**.

A regra inegociável (CLAUDE.md regra 6):

> **O Dagster é o ÚNICO escritor. A API lê APENAS um snapshot publicado, em
> `read_only=True`. Os dois nunca disputam escrita no mesmo arquivo. A publicação
> só acontece APÓS a validação.**

A solução é o padrão **blue-green / publish-pointer**: o Dagster constrói um novo
arquivo *ao lado* do que está em produção, valida, e só então troca um **ponteiro**
(`current.json`) de forma atômica. A API sempre abre o arquivo que o ponteiro
indica, em modo somente-leitura. Como o arquivo ativo nunca é reescrito no lugar,
a API jamais lê um arquivo meio-gravado.

### Mentoria rápida
1. **Negócio:** o dashboard precisa de dados estáveis e rápidos; um pipeline
   escrevendo "por baixo" de uma consulta geraria números inconsistentes na tela.
2. **Conceito (BI/data engineering):** separar **processamento** (batch, escreve)
   de **serving** (online, só lê) é o padrão de qualquer camada de serving
   analítica. O snapshot é a "foto" imutável que serve o serving.
3. **Erro de júnior:** deixar a API e o pipeline apontarem para o mesmo `.duckdb`
   "para simplificar" — funciona no happy path e corrompe/trava sob carga.
4. **Validar:** depois de publicar, abrir o arquivo em `read_only=True`, conferir
   que as 4 tabelas existem e que a receita bate com a âncora (ver §6).

---

## 2. Fonte e conteúdo do snapshot

O snapshot carrega as **4 tabelas Gold** (de `data/processed/gold/`, arquivo
Parquet único por tabela) como **tabelas físicas** dentro de um `.duckdb`:

| Tabela                          | Grão                         | Linhas  |
|---------------------------------|------------------------------|---------|
| `fct_basket`                    | 1 cesta                      | 155.848 |
| `agg_weekly_revenue`            | 1 semana                     | 53      |
| `agg_household_rfm`             | 1 domicílio                  | 2.469   |
| `agg_household_activity_month`  | 1 domicílio × mês ativo      | 24.449  |

Mais uma tabela técnica de metadados, **`_snapshot_meta`** (1 linha):

```
built_at, gold_source, revenue_total, basket_count, household_count,
git_commit, schema_version, content_hash, snapshot_version
```

O carregamento é idempotente — `CREATE OR REPLACE TABLE <t> AS SELECT * FROM
read_parquet('<gold>/<t>/<t>.parquet')`. As tabelas Gold são arquivo único (não
particionadas), então não há `hive_partitioning` aqui; se uma tabela Gold passar a
ser particionada no futuro, troque para o glob `**/*.parquet` com
`hive_partitioning=true`, como já é feito na leitura Silver.

---

## 3. Fluxo: staging → validação → publicação atômica → ponteiro

```
                         DAGSTER (único escritor)
  ┌──────────────────────────────────────────────────────────────────────┐
  │                                                                        │
  │  data/processed/gold/*.parquet   (fonte: 4 tabelas Gold já validadas)  │
  │            │                                                           │
  │            ▼                                                           │
  │  [1] BUILD em STAGING                                                  │
  │      data/snapshots/.staging/snapshot.duckdb.tmp                       │
  │      CREATE OR REPLACE TABLE ... AS SELECT * FROM read_parquet(...)    │
  │      + _snapshot_meta ; CHECKPOINT ; close                            │
  │            │                                                           │
  │            ▼                                                           │
  │  [2] VALIDAÇÃO (GATE)  — abre o staging em read_only e roda os checks  │
  │      receita==4.596.039,58 (3 tabelas) · cestas==155.848 ·            │
  │      domicílios==2.469 · 4 tabelas presentes e não-vazias             │
  │            │                                                           │
  │     falhou?├───────────────► ABORTA: remove staging, NÃO promove,     │
  │            │ sim             snapshot atual fica INTACTO, raise        │
  │            │ não                                                       │
  │            ▼                                                           │
  │  [3] PUBLICAÇÃO ATÔMICA                                                │
  │      os.replace(staging  →  snapshot_<versao>.duckdb)   (move atômico) │
  │            │                                                           │
  │            ▼                                                           │
  │  [4] PONTEIRO                                                          │
  │      escreve current.json.tmp  →  os.replace → current.json           │
  │            │                                                           │
  │            ▼                                                           │
  │  [5] RETENÇÃO: mantém os últimos N (=3) snapshots; remove os antigos   │
  │                (nunca remove o ativo)                                  │
  └──────────────────────────────────────────────────────────────────────┘
                             │  current.json aponta para o .duckdb ativo
                             ▼
                      API FastAPI (somente leitura)
          lê current.json → abre snapshot_<versao>.duckdb  read_only=True
```

**Por que atômico?** `os.replace` é uma troca atômica no mesmo volume (vale no
Windows, sem precisar de symlink). Em qualquer instante a API vê **ou** o estado
antigo **ou** o novo — nunca um arquivo pela metade nem um `current.json`
truncado. O ponteiro também é trocado via `current.json.tmp` + `os.replace`.

**Por que em staging?** Porque o arquivo que a API lê (o ativo) **nunca** é aberto
para escrita. Todo o trabalho acontece no `.staging/`, isolado.

---

## 4. Validação ANTES de publicar (o gate inegociável)

A publicação só acontece se **todos** os checks passarem (rodados sobre o staging,
em `read_only=True`). Se **qualquer** check falhar: o staging é descartado, nada é
promovido, o `current.json` e o snapshot ativo ficam **intactos**, e o asset
**falha** (`SnapshotValidationError`). Isso garante que um Gold quebrado nunca
chega à API.

As âncoras de validação (as mesmas da camada Gold — ver `docs/metrics.md §0`):

| Check                                | Regra                                             |
|--------------------------------------|---------------------------------------------------|
| `fct_basket_revenue_reconciles`      | `SUM(fct_basket.basket_revenue)` == 4.596.039,58  |
| `weekly_revenue_reconciles`          | `SUM(agg_weekly_revenue.revenue)` == 4.596.039,58 |
| `rfm_monetary_reconciles`            | `SUM(agg_household_rfm.monetary_value)` == 4.596.039,58 |
| `basket_count_matches`               | `COUNT(*) fct_basket` == 155.848                  |
| `household_count_matches`            | `COUNT(*) agg_household_rfm` == 2.469             |
| `<tabela>_present_non_empty` (×4)    | cada uma das 4 tabelas existe e tem ≥ 1 linha     |

Tolerância da receita: `0,01` (ruído de ponto flutuante; qualquer fan-out erraria
por milhares de dólares). As três reconciliações de receita provam que o snapshot
carregou os dados **sem perda nem dupla contagem** — se as três batem no mesmo
valor por caminhos diferentes (cesta, semana, domicílio), a carga está íntegra.

Dois asset checks estruturais extra rodam sobre o arquivo **já publicado**:

| Check                                 | Prova                                              |
|---------------------------------------|----------------------------------------------------|
| `current_json_points_to_existing_file`| o `active` do `current.json` existe em disco       |
| `snapshot_opens_read_only`            | o arquivo abre em `read_only=True` com as 4 tabelas|

---

## 5. Versionamento, nomes e retenção

**Nome do arquivo:** `snapshot_<versao>.duckdb`, onde

```
<versao> = <timestamp UTC compacto>_<hash curto do conteúdo Gold>
         =  20261014T185313Z       _ 02f45a3e3a46
```

- **`content_hash`** = SHA-256 (12 hex) dos 4 Parquet Gold, em ordem estável.
  É **determinístico**: o mesmo Gold ⇒ o mesmo hash. Serve para saber, de relance,
  se dois snapshots têm o mesmo conteúdo.
- **`timestamp`** varia a cada build — **por design**, como o `_ingested_at` da
  Bronze. Ele registra *quando* publicamos, não *o quê*. Portanto, dois rebuilds do
  mesmo Gold produzem o mesmo `content_hash` mas nomes diferentes (timestamp). O
  conteúdo das tabelas é equivalente; o artefato é sempre validado e publicado
  atomicamente. (O byte-a-byte do `.duckdb` também difere porque o formato embute o
  timestamp — isso é esperado e não afeta a reprodutibilidade analítica.)

**Ponteiro `current.json`** (o contrato que a API lê):

```json
{
  "active": "snapshot_20261014T185313Z_02f45a3e3a46.duckdb",
  "version": "20261014T185313Z_02f45a3e3a46",
  "schema_version": "1",
  "published_at": "2026-10-14T18:53:13+00:00",
  "built_at": "2026-10-14T18:53:13+00:00",
  "revenue_total": 4596039.58,
  "basket_count": 155848,
  "household_count": 2469,
  "git_commit": "b4cbd6c",
  "content_hash": "02f45a3e3a46",
  "tables": ["fct_basket", "agg_weekly_revenue", "agg_household_rfm", "agg_household_activity_month"],
  "checks": "passed"
}
```

**Retenção:** mantemos os **últimos 3** snapshots (`RETENTION_COUNT`) para permitir
rollback; os mais antigos são removidos após uma publicação bem-sucedida. O
snapshot **ativo nunca é removido**, mesmo que caia fora da janela dos 3 mais
recentes.

---

## 6. Rollback

Rollback é apenas **reescrever o ponteiro** para uma versão anterior que ainda
exista em disco (por isso guardamos os últimos 3). Como `current.json` é a única
fonte de verdade de "qual arquivo está ativo", trocar o ponteiro troca a versão
servida — sem reprocessar nada.

Passo a passo (manual, no diretório `data/snapshots/`):

1. Liste os snapshots disponíveis: `ls data/snapshots/snapshot_*.duckdb`.
2. Escolha a versão-alvo (ex. a penúltima).
3. Reescreva `current.json` apontando `active`/`version` para ela — de preferência
   com a mesma troca atômica (escrever `current.json.tmp` e `os.replace`), para a
   API não pegar um ponteiro truncado.
4. Opcional: confirme com os asset checks estruturais (o arquivo existe e abre em
   `read_only`).

> Não há rollback automático além disso (MVP). Se a versão-alvo já tiver sido
> removida pela retenção, basta re-materializar o Gold e republicar.

---

## 7. Contrato de leitura da API (próxima fase — NÃO implementar agora)

A API **nunca** escreve e **nunca** acessa o DuckDB fora deste contrato:

1. Ler `data/snapshots/current.json` e pegar o campo `active`.
2. Abrir `data/snapshots/<active>` com **`duckdb.connect(path, read_only=True)`**.
3. (Opcional) conferir `schema_version` — recusar versões não suportadas.
4. Consultar apenas as tabelas publicadas. **Nunca** executar SQL arbitrário vindo
   do frontend (CLAUDE.md regra 7); as queries são fixas no backend.
5. Em produção, reabrir a conexão quando `current.json.active` mudar (hot-swap), ou
   abrir por requisição — nunca manter um handle de escrita.

Esqueleto de referência (ilustrativo):

```python
import json, pathlib, duckdb

SNAP = pathlib.Path("data/snapshots")

def open_active():
    cur = json.loads((SNAP / "current.json").read_text(encoding="utf-8"))
    return duckdb.connect(str(SNAP / cur["active"]), read_only=True)
```

---

## 8. Como materializar (manual, MVP — sem schedules)

```bash
# A partir de pipelines/ (venv com dagster/duckdb instalados):
.venv/Scripts/python.exe -m dagster asset materialize -m crm_pipelines \
    --select "snapshot/published_snapshot"
```

Pré-requisito: as 4 tabelas Gold já materializadas em `data/processed/gold/`
(o asset `published_snapshot` depende explicitamente de `gold/*`). O pipeline
inteiro ponta a ponta:

```bash
.venv/Scripts/python.exe -m dagster asset materialize -m crm_pipelines --select "*"
```

Artefatos (todos gitignored — reprodutíveis):
`data/snapshots/snapshot_<versao>.duckdb`, `data/snapshots/current.json`,
`data/snapshots/.staging/` (transitório).
