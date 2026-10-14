"""Customer Intelligence Lab — API FastAPI read-only.

Serve os dados do Overview a partir do snapshot DuckDB publicado pelo Dagster.
A API NUNCA escreve e NUNCA executa SQL vindo do frontend (CLAUDE.md regras 6 e 7).
"""
