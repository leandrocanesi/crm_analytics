# HANDOFF — estado do projeto (retomar aqui após o restart)

**Data:** 2026-10-14 · **Fase atual:** 1 (infraestrutura) — *parcial*

## Concluído
- Ambiente inspecionado: Node v22.14, npm 11 (sem pnpm), Python 3.13 (`python`), git 2.47. Projeto no OneDrive com espaços/acento no caminho (atenção a locks/sync).
- Estrutura do monorepo criada: `frontend/ backend/ pipelines/ sql/{bronze,silver,gold} data/{raw,processed,snapshots} docs/ tests/`.
- **Equipe de agentes** criada em `.claude/agents/`: `data-architect`, `analytics-engineer`, `backend-engineer`, `frontend-engineer`, `analytics-mentor`, `qa-engineer`, `devops-engineer`.
- Documentação raiz: `README.md`, `CLAUDE.md`, `.env.example`, `.gitignore`, `docs/download-data.md`.
- Git inicializado e primeiro commit.

## Por que reiniciamos
Agentes customizados em `.claude/agents/` só são **registrados no (re)início** da sessão do Claude Code. Após reiniciar, os tipos `data-architect`, `backend-engineer`, etc. ficam invocáveis pelo maestro.

## Próximo passo (retomar a Fase 1)
Concluir o scaffold (foi iniciado e revertido para estado limpo antes do restart):
1. **backend** (agente `backend-engineer`): venv + FastAPI (`app/main.py`, `config.py`, `db/duckdb.py`, `schemas/common.py`, `routes/health.py`, `routes/meta.py`, `services/meta_service.py`), `requirements.txt`, `pyproject.toml` (ruff+pytest), teste de health/meta. Endpoints `/health` e `/meta` (meta: `snapshot_available=False` enquanto não há dados). Verificar com `ruff` + `pytest`.
2. **frontend** (agente `frontend-engineer`): Vite react-ts + Tailwind v4 + shadcn + TanStack Query + React Router; layout com sidebar; **Overview** consumindo `/health` e `/meta` com estados loading/erro/vazio; `.env.example` (`VITE_API_BASE_URL`). Verificar com `lint` + `tsc --noEmit` + `build`.
3. **devops-engineer**: quando o usuário enviar o **link do repositório GitHub**, configurar `remote origin` e fazer push.

## Pendências / decisões em aberto
- Link do repositório GitHub (usuário vai enviar) → configurar remote + push.
- Fase 2 só começa após o usuário baixar os dados reais para `data/raw/` (ver `docs/download-data.md`). Nada de dados falsos no lugar.

## Lembretes de projeto
- Dagster = único escritor do DuckDB; API = leitura read-only de snapshots publicados.
- Não inventar campos; inspecionar CSVs reais antes de modelar.
- Domicílio ≠ indivíduo. Evitar dupla contagem de receita. Correlação ≠ causalidade.
- Não usar data atual como referência de métricas históricas.
