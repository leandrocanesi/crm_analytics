"""Aplicação FastAPI read-only do Customer Intelligence Lab.

Monta CORS a partir do .env, registra os routers (thin controllers) e um handler
de erro centralizado que traduz ``SnapshotUnavailableError`` em HTTP 503 tipado.
A API só expõe GET e nunca escreve no DuckDB (CLAUDE.md regras 6 e 7).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .deps import get_snapshot
from .routers import health, meta, overview, retention, revenue, rfm
from .schemas import ErrorResponse
from .snapshot import SnapshotUnavailableError


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Nada a pré-carregar: a conexão read-only abre sob demanda (hot-swap).
    yield
    # Fecha a conexão do snapshot ao desligar.
    get_snapshot().close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=(
            "API read-only que serve o Overview do Customer Intelligence Lab a "
            "partir do snapshot DuckDB publicado pelo pipeline Dagster. Os valores "
            "monetários são da AMOSTRA de domicílios do painel 84.51°/dunnhumby, "
            "não o faturamento da rede. Datas ancoradas em 2018-01-01."
        ),
        lifespan=lifespan,
        responses={503: {"model": ErrorResponse, "description": "Snapshot indisponível"}},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.exception_handler(SnapshotUnavailableError)
    async def _snapshot_unavailable_handler(
        _request: Request, exc: SnapshotUnavailableError
    ) -> JSONResponse:
        body = ErrorResponse(status="snapshot_unavailable", detail=str(exc))
        return JSONResponse(status_code=503, content=body.model_dump())

    app.include_router(health.router)
    app.include_router(meta.router)
    app.include_router(overview.router)
    app.include_router(revenue.router)
    app.include_router(rfm.router)
    app.include_router(retention.router)
    return app


app = create_app()
