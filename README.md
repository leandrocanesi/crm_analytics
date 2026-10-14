# Customer Intelligence Lab

Plataforma de estudo e prática de **Marketing Analytics, CRM Analytics e Business Intelligence**, simulando a área de Customer Intelligence de um grande varejo sobre o dataset público **"The Complete Journey" da dunnhumby**.

> Projeto educacional e técnico. Distingue explicitamente **dados reais** (dunnhumby), **dados derivados** e **dados sintéticos** (rotulados como simulados). Métricas usam datas coerentes com o período do dataset, não a data atual. Correlação não é tratada como causalidade.

## Stack
- **Frontend**: React + TypeScript (strict) + Vite + Tailwind + shadcn/ui + Recharts + TanStack Query + React Router
- **Backend**: Python + FastAPI + Pydantic (API REST tipada, read-only sobre DuckDB)
- **Dados**: DuckDB + SQL + Parquet
- **Orquestração**: Dagster (software-defined assets, asset checks)
- **Qualidade**: Ruff, Pytest, ESLint, TypeScript strict

## Estrutura do monorepo
```
frontend/   # UI React/Vite
backend/    # API FastAPI (lê snapshots publicados)
pipelines/  # Dagster: assets bronze/silver/gold + checks
sql/        # bronze/ silver/ gold/  (SQL de transformação)
data/       # raw/ (originais, não versionados) processed/ snapshots/
docs/       # dicionário de dados, modelo, snapshots, download dos dados
tests/
```

## Arquitetura de dados (medalhão)
- **raw** → arquivos originais da dunnhumby (intocados, fora do git)
- **Bronze** → ingestão fiel + metadados técnicos
- **Silver** → tipagem, limpeza, padronização, integridade
- **Gold** → tabelas analíticas prontas para a API (grão explícito)

O **Dagster** materializa e **publica snapshots DuckDB apenas após validação**; a **API** consulta esses snapshots em **somente leitura**. API e Dagster nunca disputam escrita no mesmo arquivo.

## Dados (dunnhumby)
Os dados **não acompanham o repositório**. Siga `docs/download-data.md` para baixar "The Complete Journey" em https://www.dunnhumby.com/source-files/ e colocar os CSVs em `data/raw/`.

## Como rodar (após a Fase 1)
### Backend
```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
# http://localhost:8000/health  |  /docs (OpenAPI)
```
### Frontend
```bash
cd frontend
npm install
cp .env.example .env     # ajuste VITE_API_BASE_URL se necessário
npm run dev              # http://localhost:5173
```

## Roadmap (fases)
- **Fase 1** — Infra: monorepo, frontend, backend, healthchecks, docs. ⬅️ *em andamento*
- **Fase 2** — Ingestão mínima de dados reais, Dagster, Bronze/Silver/Gold, testes.
- **Fase 3** — Modelagem analítica, métricas iniciais, endpoints, Overview com dados reais.
- **Fase 4** — Customer 360, Segmentação RFM, Coortes.
- **Fase 5** — Campanhas, Cupons, mensuração promocional, Data Explorer, qualidade/observabilidade.

## Páginas previstas
Overview (primeira) · Customer 360 · Segmentation · Cohort Analytics · Campaign Intelligence · Data Explorer · Data Operations.

## Licença / uso dos dados
Respeite os termos de uso do dataset da dunnhumby. Este repositório não redistribui os dados originais.
