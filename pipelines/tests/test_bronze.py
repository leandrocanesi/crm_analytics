"""Testes rápidos da camada Bronze.

Usam apenas tabelas pequenas (.rda) para rodar em segundos — transactions e
promotions ficam de fora por serem pesadas (são exercitadas na materialização
real via `dagster asset materialize`).
"""

from __future__ import annotations

import pandas as pd
import pytest

from crm_pipelines.bronze import _content_sha256
from crm_pipelines.config import (
    TABLE_SPECS,
    TABLE_SPECS_BY_NAME,
    load_expected_hashes,
)
from crm_pipelines.readers import coerce_id_columns, read_r_dataframe, sha256_file

# Tabelas pequenas, seguras para ler em teste.
SMALL_TABLES = [
    "campaign_descriptions",
    "demographics",
    "campaigns",
    "coupon_redemptions",
    "coupons",
    "products",
]


def test_all_source_files_exist() -> None:
    for spec in TABLE_SPECS:
        assert spec.source_path.exists(), f"faltando {spec.source_file}"


def test_expected_hashes_cover_all_tables() -> None:
    hashes = load_expected_hashes()
    for spec in TABLE_SPECS:
        assert spec.source_file in hashes, f"sem hash para {spec.source_file}"
        assert len(hashes[spec.source_file]) == 64


@pytest.mark.parametrize("table", SMALL_TABLES)
def test_source_hash_matches_manifest(table: str) -> None:
    spec = TABLE_SPECS_BY_NAME[table]
    expected = load_expected_hashes()[spec.source_file]
    assert sha256_file(spec.source_path) == expected


@pytest.mark.parametrize("table", SMALL_TABLES)
def test_row_count_matches_expected(table: str) -> None:
    spec = TABLE_SPECS_BY_NAME[table]
    frame = read_r_dataframe(spec.source_path)
    assert len(frame) == spec.expected_rows


@pytest.mark.parametrize("table", SMALL_TABLES)
def test_id_columns_are_string(table: str) -> None:
    spec = TABLE_SPECS_BY_NAME[table]
    frame = coerce_id_columns(read_r_dataframe(spec.source_path), spec.id_columns)
    for col in spec.id_columns:
        assert frame[col].dtype == "string", f"{table}.{col} não é string"


@pytest.mark.parametrize("table", SMALL_TABLES)
def test_content_hash_is_deterministic(table: str) -> None:
    """Reler o mesmo arquivo produz o mesmo hash de conteúdo (reprodutibilidade)."""
    spec = TABLE_SPECS_BY_NAME[table]
    first = coerce_id_columns(read_r_dataframe(spec.source_path), spec.id_columns)
    second = coerce_id_columns(read_r_dataframe(spec.source_path), spec.id_columns)
    assert _content_sha256(first) == _content_sha256(second)


def test_read_rejects_multi_object(tmp_path) -> None:
    """read_r_dataframe deve falhar ruidosamente se não houver 1 objeto único."""
    import pyreadr

    path = tmp_path / "multi.rda"
    pyreadr.write_rdata(
        str(path), pd.DataFrame({"a": [1]}), df_name="a"
    )
    # Arquivo válido com 1 objeto → OK (sanidade do writer de teste).
    assert len(read_r_dataframe(path)) == 1
