# CI — Customer Intelligence Lab

O workflow [`workflows/ci.yml`](workflows/ci.yml) roda em `push` (main/master) e em
todo `pull_request`. Ele **valida código, não dados**.

## Por que o CI não roda os testes de dados

O runner do GitHub **não tem os dados da dunnhumby**. Por licença (84.51°) e tamanho,
`data/raw/` (os `.rds`/`.rda`), `data/processed/` (Parquet) e `data/snapshots/`
(`.duckdb`) são gitignored — só metadados leves de `data/raw/` são versionados.
Materializar o pipeline no CI seria inviável e proibido pela licença.

Portanto o CI exercita o que roda **sem dados**: lint, tipos, build e os testes que
não tocam o disco. Os testes de integração se auto-pulam.

## Jobs

| Job | Setup | O que roda |
|-----|-------|------------|
| **pipelines** | Python 3.13 | `ruff check` + `pytest`. Os testes que leem Parquet/`.rds`/`.rda` pulam via `skipif` de existência do artefato; só os puros (resolução de SQL, lógica de segmento RFM, comparadores de check) rodam. |
| **backend** | Python 3.13 | `ruff check` + `pytest`. Os testes de contrato exigem um snapshot publicado; sem ele, a suíte inteira pula (ver `backend/tests/conftest.py`). |
| **frontend** | Node 22 | `npm ci` + `npm run lint` + `npx tsc --noEmit` + `npm run build`. Estáticos, não precisam da API no ar. |

Cada suíte Python roda com `-rs` para listar no log os testes pulados e o motivo —
transparência: o verde do CI é "código OK", não "dados validados".

## Como rodar as verificações completas (com dados) localmente

```bash
# Pipelines
cd pipelines && .venv/Scripts/python.exe -m ruff check crm_pipelines tests \
  && .venv/Scripts/python.exe -m pytest -q

# Backend
cd backend && .venv/Scripts/python.exe -m ruff check app tests \
  && .venv/Scripts/python.exe -m pytest -q

# Frontend
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```

Com os dados materializados e um snapshot publicado, as suítes rodam na íntegra
(nada pula). Essa é a diferença entre o verde local (dados + código) e o verde do
CI (só código).
