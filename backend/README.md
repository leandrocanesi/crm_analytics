# Backend — Customer Intelligence Lab API

API **read-only** em FastAPI que serve o Overview a partir do **snapshot DuckDB
publicado** pelo pipeline Dagster. A API nunca escreve no DuckDB e nunca executa
SQL vindo do frontend (CLAUDE.md regras 6 e 7).

## Arquitetura

```
app/
  main.py        app FastAPI: CORS, routers, handler de erro (503 tipado)
  config.py      Settings (pydantic-settings): SNAPSHOTS_DIR, CORS, título/versão
  deps.py        injeção de dependências (SnapshotManager singleton)
  snapshot.py    acesso read-only: lê current.json → abre .duckdb ativo (hot-swap)
  queries.py     SQL predefinido e parametrizado (nunca SQL do cliente)
  services.py    lógica de analytics (consulta → monta contratos)
  schemas.py     modelos Pydantic de resposta (contratos estáveis / OpenAPI)
  routers/       endpoints GET: health, meta, overview, revenue, rfm
tests/           testes de contrato (pytest + TestClient) contra o snapshot real
```

O arquivo `.duckdb` ativo **não** é fixo em config: é resolvido em runtime via
`data/snapshots/current.json`. Quando o pipeline publica uma nova versão (troca
atômica do ponteiro), a API detecta a mudança de `active` e reabre a conexão
(hot-swap) — ver `docs/snapshots.md` §7.

## Setup

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Variáveis de ambiente (opcionais; há defaults sensatos) — copie `.env.example` da
raiz para `.env`:

| Var | Default | O que é |
|---|---|---|
| `API_TITLE` | `Customer Intelligence Lab API` | título no OpenAPI |
| `API_VERSION` | `0.1.0` | versão da API |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | origens do frontend |
| `SNAPSHOTS_DIR` | `../data/snapshots` | diretório dos snapshots (relativo a `backend/`) |
| `SCHEMA_VERSION_SUPPORTED` | `1` | contrato de snapshot aceito |
| `AS_OF_DATE` | `2018-01-01` | data de referência fixa do dataset |
| `CURRENCY` | `USD` | moeda dos valores |

## Rodar

```bash
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

- Docs interativas (OpenAPI): http://localhost:8000/docs
- Pré-requisito: um snapshot publicado em `data/snapshots/` (materialize
  `snapshot/published_snapshot` no Dagster). Sem ele, `/health` responde
  `snapshot_available=false` e os endpoints de dados retornam **503**.

## Qualidade

```bash
cd backend
.venv/Scripts/python.exe -m ruff check app tests
.venv/Scripts/python.exe -m pytest -q
```

Os testes de contrato reconciliam com as âncoras do snapshot real: receita
`4.596.039,58`, `155.848` cestas, `2.469` domicílios, `53` semanas, ticket médio
`≈ 29,49`, `7` segmentos RFM.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | status da API + se o snapshot está disponível |
| GET | `/meta` | metadados do snapshot (versão, built_at, âncoras, as-of, git_commit) |
| GET | `/overview` | cards: receita, domicílios ativos, cestas, ticket médio |
| GET | `/revenue/weekly` | série de receita semanal (53 semanas) |
| GET | `/rfm/segments` | distribuição dos 7 segmentos RFM |

> Escopo da receita: é a receita da **amostra** de ~2.469 domicílios do painel
> 84.51°/dunnhumby, **não** o faturamento da rede (metrics.md §0.1). Datas
> ancoradas em `2018-01-01`, nunca na data atual.
