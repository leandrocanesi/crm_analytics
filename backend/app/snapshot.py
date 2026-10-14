"""Camada de acesso read-only ao snapshot DuckDB (o "db/" da API).

Contrato (``docs/snapshots.md`` §7, CLAUDE.md regras 6 e 7):

1. Ler ``<snapshots_dir>/current.json`` e pegar o campo ``active``.
2. Abrir ``<snapshots_dir>/<active>`` com ``duckdb.connect(path, read_only=True)``.
3. Conferir ``schema_version`` — recusar versões não suportadas.
4. Consultar apenas as tabelas publicadas, com SQL **fixo** no backend e parâmetros
   ligados (bind) — NUNCA interpolar string vinda do frontend.
5. Reabrir a conexão quando ``current.json.active`` mudar (hot-swap).

A API **nunca** abre o arquivo para escrita e **nunca** disputa o arquivo com o
Dagster (que escreve sempre em staging e troca o ponteiro atomicamente).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import duckdb


class SnapshotUnavailableError(RuntimeError):
    """Não há snapshot utilizável: ponteiro/arquivo ausente ou schema incompatível.

    O handler da API traduz isto em HTTP 503 (serviço indisponível), com mensagem
    clara — é um estado operacional esperado (ex.: pipeline ainda não publicou),
    não um bug.
    """


class SnapshotManager:
    """Abre e consulta o snapshot ativo em read-only, com hot-swap por requisição.

    Thread-safe: um ``Lock`` serializa a (re)abertura e as consultas. Para uma
    aplicação de serving analítico read-only de baixa concorrência isto é simples
    e suficiente; a conexão DuckDB nunca é compartilhada sem o lock.
    """

    CURRENT_FILENAME = "current.json"

    def __init__(self, snapshots_dir: Path, *, supported_schema: str = "1") -> None:
        self._dir = Path(snapshots_dir)
        self._supported = str(supported_schema)
        self._lock = threading.Lock()
        self._con: duckdb.DuckDBPyConnection | None = None
        self._active: str | None = None
        self._pointer: dict[str, Any] | None = None

    # -- ponteiro -----------------------------------------------------------
    @property
    def current_json(self) -> Path:
        return self._dir / self.CURRENT_FILENAME

    def _read_pointer(self) -> dict[str, Any]:
        cj = self.current_json
        if not cj.exists():
            raise SnapshotUnavailableError(
                f"Ponteiro de snapshot ausente ({cj}). "
                "O pipeline Dagster ainda não publicou um snapshot?"
            )
        try:
            data = json.loads(cj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise SnapshotUnavailableError(f"current.json ilegível: {exc}") from exc

        active = data.get("active")
        if not active:
            raise SnapshotUnavailableError("current.json não contém o campo 'active'.")

        schema = str(data.get("schema_version", ""))
        if schema != self._supported:
            raise SnapshotUnavailableError(
                f"schema_version do snapshot ('{schema}') não é suportado por esta "
                f"API (esperado '{self._supported}'). Atualize a API ou o snapshot."
            )
        return data

    # -- conexão (hot-swap) -------------------------------------------------
    def _ensure(self) -> duckdb.DuckDBPyConnection:
        """Garante uma conexão read-only para o arquivo ativo atual. (com lock)."""
        pointer = self._read_pointer()
        active = pointer["active"]
        if self._con is None or active != self._active:
            path = self._dir / active
            if not path.exists():
                raise SnapshotUnavailableError(
                    f"current.json aponta para '{active}', mas o arquivo não existe "
                    f"em {path}."
                )
            if self._con is not None:
                try:
                    self._con.close()
                except Exception:  # noqa: BLE001 — fechar é best-effort.
                    pass
            try:
                self._con = duckdb.connect(str(path), read_only=True)
            except duckdb.Error as exc:
                self._con = None
                raise SnapshotUnavailableError(
                    f"Falha ao abrir o snapshot em read-only: {exc}"
                ) from exc
            self._active = active
        self._pointer = pointer
        return self._con

    # -- API interna --------------------------------------------------------
    def pointer(self) -> dict[str, Any]:
        """Conteúdo atual de current.json (após validar e garantir a conexão)."""
        with self._lock:
            self._ensure()
            assert self._pointer is not None
            return dict(self._pointer)

    def query(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Executa SQL **fixo do backend** (nunca do cliente) e devolve dicts.

        ``params`` são ligados via placeholders ``?`` do DuckDB (bind), jamais
        concatenados na string — é a única forma de passar valores dinâmicos.
        """
        with self._lock:
            con = self._ensure()
            cur = con.execute(sql, list(params)) if params else con.execute(sql)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def query_one(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> dict[str, Any]:
        """Como :meth:`query`, mas espera exatamente uma linha."""
        rows = self.query(sql, params)
        if not rows:
            raise SnapshotUnavailableError("Consulta de agregação não retornou linhas.")
        return rows[0]

    def available(self) -> bool:
        """True se um snapshot válido pode ser aberto agora (para o /health)."""
        with self._lock:
            try:
                self._ensure()
                return True
            except SnapshotUnavailableError:
                return False

    def close(self) -> None:
        with self._lock:
            if self._con is not None:
                try:
                    self._con.close()
                finally:
                    self._con = None
                    self._active = None
                    self._pointer = None
