# CLAUDE.md — Customer Intelligence Lab

Guia operacional para agentes de IA (e humanos) que trabalham neste repositório.

## O que é
Aplicação web para **estudar e praticar Marketing Analytics, CRM Analytics e Business Intelligence**, simulando a área de Customer Intelligence de um grande varejo. Fonte de dados: dataset público **"The Complete Journey" da dunnhumby** (https://www.dunnhumby.com/source-files/).

Objetivo duplo: (1) construir uma plataforma funcional e profissional; (2) o usuário adquirir competência prática em CRM/Marketing Analytics/BI. Por isso, **todo trabalho relevante vem acompanhado de mentoria curta e objetiva**.

## Equipe de agentes (orquestração)
O **maestro** é a sessão principal do Claude Code (conversa com o usuário e delega). Especialistas em `.claude/agents/`:
- `data-architect` — modelagem bronze/silver/gold, granularidade, dicionário de dados, estratégia DuckDB/snapshots/concorrência.
- `analytics-engineer` — Dagster (SDAs, asset checks), SQL de transformação, Parquet, idempotência.
- `backend-engineer` — FastAPI/Pydantic, API read-only, contratos.
- `frontend-engineer` — React/TS/Vite/Tailwind/shadcn/Recharts/TanStack Query/Router.
- `analytics-mentor` — definição rigorosa de métricas (RFM, coortes, retenção) e ensino.
- `qa-engineer` — pytest, ruff, eslint, tsc strict, asset checks.
- `devops-engineer` — git/GitHub, .gitignore, versionamento, DevOps.

> Agentes customizados só são carregados quando a sessão do Claude Code (re)inicia.

## Stack (NÃO alterar sem aprovação)
- **Frontend**: React, TypeScript (strict), Vite, Tailwind, shadcn/ui, Recharts, TanStack Query, React Router.
- **Backend**: Python, FastAPI, Pydantic.
- **Dados**: DuckDB, SQL, Parquet, Pandas (só quando necessário).
- **Orquestração**: Dagster (software-defined assets, asset checks, materializações observáveis).
- **Qualidade**: Git, Ruff, Pytest, ESLint, TypeScript strict.
- **PROIBIDO sem necessidade concreta + aprovação**: Redis, Kafka, Airflow, Spark, Kubernetes, PostgreSQL.

## Arquitetura (monorepo)
```
crm_analytics/              # raiz do monorepo
  frontend/                 # React + Vite
  backend/                  # FastAPI (API read-only)
  pipelines/                # Dagster (assets bronze/silver/gold, checks)
  sql/{bronze,silver,gold}/ # SQL de transformação por camada
  data/{raw,processed,snapshots}/
  docs/                     # dicionário de dados, modelo, snapshots, download
  tests/
```

### Camadas de dados
- **raw** (`data/raw/`): arquivos originais da dunnhumby, **intocados**, **não versionados**.
- **Bronze**: ingestão fiel + metadados técnicos (origem, timestamp, linhas).
- **Silver**: tipagem, limpeza, padronização, normalização de datas, integridade.
- **Gold**: tabelas/visões analíticas prontas para a API, com **grão explícito**.

## Regras inegociáveis
1. **Nunca inventar campos** nem presumir a estrutura dos CSVs — inspecionar os arquivos reais primeiro.
2. Distinguir **dados reais da dunnhumby × derivados × sintéticos** (sintéticos sempre rotulados como simulados).
3. **Domicílio (`household`) ≠ indivíduo identificado.**
4. **Evitar dupla contagem de receita** em joins com produto/cupom/campanha; definir a fonte única de verdade da receita.
5. Transformações **idempotentes e reprodutíveis**.
6. **DuckDB — concorrência**: o **Dagster é o único escritor**; a **API lê apenas snapshots publicados em read-only**. Nunca disputar escrita no mesmo arquivo. Publicação de snapshot só **após validação** (ver `docs/snapshots.md`).
7. **Nunca executar SQL arbitrário vindo do frontend.** O frontend nunca acessa o DuckDB direto.
8. **Não usar a data atual do computador** como referência para métricas históricas — usar datas coerentes com o período do dataset.
9. **Correlação ≠ causalidade** (especialmente em análises pré/pós-campanha, sem grupo de controle).
10. `data/raw/`, `.env`, `.venv/`, `node_modules/`, `*.duckdb`, `*.parquet` **não** vão para o git.

## Métricas (definir com `analytics-mentor` ANTES de implementar)
Para cada métrica, especificar: definição, numerador, denominador, grão, janela temporal, data de referência, filtros e limitações. Escopo: receita observada, clientes/domicílios ativos, frequência, ticket médio por cesta, recência, valor monetário, RFM, retenção, recompra, coortes, participação em campanha, resgate de cupom, pré/pós-campanha.

## Comandos (serão preenchidos ao fim da Fase 1)
```bash
# Backend
cd backend && python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
.venv/Scripts/python.exe -m ruff check app tests && .venv/Scripts/python.exe -m pytest -q

# Frontend
cd frontend && npm install
npm run dev          # Vite em :5173
npm run lint && npx tsc --noEmit && npm run build
```

## Processo
Trabalhar em **fases** (ver README). Em cada fase: apresentar plano antes de grandes mudanças, implementar em incrementos pequenos, rodar verificações, corrigir, documentar decisões, reportar o que foi feito e o que falta. **Não** implementar fases futuras antecipadamente. Decisões importantes de modelagem/métrica são **discutidas com o usuário antes**.

## Ambiente
Windows 11, Node v22.14, npm 11 (sem pnpm), Python 3.13 (`python`, não `python3`), git 2.47. Projeto dentro do OneDrive com espaços/acento no caminho — usar aspas em paths e manter artefatos pesados fora do git/OneDrive.
