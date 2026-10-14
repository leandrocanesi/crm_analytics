# HANDOFF — estado do projeto (retomar aqui)

**Data:** 2026-10-14 · **Último commit sincronizado em `origin/main`:** `d072547` (backend).

> Checkpoint durável: mesmo que a sessão do Claude acabe, **os arquivos em disco persistem**. Este doc + a memória do projeto bastam para retomar sem perder evolução.

## Âncoras do dataset (imutáveis — qualquer número que as contradiga está errado)
- Fonte: **84.51° "The Complete Journey"** (pacote R `completejourney`, público). NÃO é a release original dunnhumby. Originais `.rds`/`.rda` em `data/raw/completejourney/` (gitignored; proveniência + SHA256 versionados).
- Receita observada total = **US$ 4.596.039,58** · cestas = **155.848** · domicílios = **2.469** · linhas = 1.469.307.
- Data de referência (as-of) = **2018-01-01** (máx. observada). NUNCA usar a data de hoje.

## Concluído, validado e commitado (origin/main)
| Camada | Commit | Estado |
|---|---|---|
| Bronze (Dagster) | `05477e0` | `.rds`→Parquet 1:1, asset checks |
| Métricas (doc) | `1772116` | `docs/metrics.md` APROVADO (decisões 1–5 + segmentos RFM) |
| Silver | `2966d0c` | tipagem DECIMAL, flags, dedupe coupons, FK checks WARN |
| Gold | `b4cbd6c` | `fct_basket`, `agg_weekly_revenue`, `agg_household_rfm`, `agg_household_activity_month` |
| Snapshot | `7cc2947` | `.duckdb` read-only via `current.json` (publicação atômica); `docs/snapshots.md` |
| Backend | `d072547` | FastAPI read-only; endpoints `/health /meta /overview /revenue/weekly /rfm/segments` |

Receita reconcilia 4.596.039,58 de ponta a ponta (Bronze→Gold→Snapshot→API). Pipeline+API 100% funcionais.

## EM CONSTRUÇÃO (não commitado) — Frontend
- `frontend-engineer` rodando em background quando este handoff foi escrito. `frontend/` tem o scaffold Vite (package.json, vite.config.ts, tsconfig, index.html); `src/` sendo escrito.
- Stack: React+Vite+TS strict+Tailwind+shadcn/ui+Recharts+TanStack Query+Router. Página **Overview** em **bento grid minimalista-maximalista**.
- Paleta (derivada de referências do usuário, só cores — NÃO copiar marca): petróleo/teal `#042624→#1A7268(primária)→#C3E2DC` + dourado âmbar acento `#E0A24A`. Light+dark via tokens. Ver memória `design-direction-ui`.
- Consome os 5 endpoints da API (base `VITE_API_BASE_URL=http://localhost:8000`).

### Como retomar o frontend
1. `ls frontend/src` — ver se o agente concluiu (componentes, Overview, cliente de API).
2. Se completo: `cd frontend && npm install && npm run lint && npx tsc --noEmit && npm run build`. Subir API (`cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`) + `npm run dev` e conferir a Overview renderizando.
3. Se verde: commit+push **inline na main** (agentes não fazem git — classificador bloqueia push de subagente).
4. Se `frontend/src` estiver vazio/incompleto: relançar `frontend-engineer` com o briefing (paleta + bento + endpoints acima).

## Hábito de trabalho / git
- Fluxo: delegar a agente especialista → **validar o resultado de forma independente** (ler Parquet/snapshot/endpoints e conferir âncoras) → commit+push inline na main.
- Push direto na main AUTORIZADO pelo usuário; fazer inline (não via subagente).

## Comandos-chave
- Pipeline: `cd pipelines && .venv/Scripts/dagster.exe asset materialize -m crm_pipelines --select "*"` · qualidade `.venv/Scripts/python.exe -m ruff check crm_pipelines tests && ... -m pytest -q`
- Backend: `cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000` (docs em /docs)

## Próximos passos após o frontend
- QA transversal (`qa-engineer`). Novas páginas além da Overview. Métrica de retenção derivada de `agg_household_activity_month` (filtrar mês-fronteira parcial 2018-01). Snapshot `docs/snapshots.md` já cobre rollback.
