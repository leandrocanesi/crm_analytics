"""Leitura fiel de arquivos binários R (.rds/.rda) e utilitários de hashing.

Camada fina sobre ``pyreadr``. Nenhuma limpeza semântica acontece aqui — apenas
extração 1:1 do DataFrame e normalização mínima exigida pela Bronze (IDs como
string). Qualquer dedupe/tipagem/integridade é responsabilidade da Silver.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pyreadr

# Lê em blocos para não carregar o arquivo inteiro na memória ao calcular o hash
# (promotions.rds tem ~25 MB; transactions.rds ~13 MB — barato, mas mantemos o
# padrão de streaming por boa prática).
_HASH_CHUNK_BYTES = 1 << 20  # 1 MiB


def sha256_file(path: Path) -> str:
    """SHA-256 (hex minúsculo) do conteúdo do arquivo, lendo em blocos."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_r_dataframe(path: Path) -> pd.DataFrame:
    """Lê um ``.rds`` ou ``.rda`` e devolve o único DataFrame contido.

    - ``.rds``: um único objeto serializado (``pyreadr`` usa a chave ``None``).
    - ``.rda``: um ou mais objetos nomeados; nesta base cada arquivo carrega
      exatamente um DataFrame, então pegamos o primeiro.

    Levanta ``ValueError`` se o arquivo não contiver exatamente um objeto, para
    falhar ruidosamente em vez de ingerir a tabela errada silenciosamente.
    """
    result = pyreadr.read_r(str(path))
    objects = list(result.values())
    if len(objects) != 1:
        names = list(result.keys())
        raise ValueError(
            f"Esperado exatamente 1 objeto em {path.name}, "
            f"encontrados {len(objects)}: {names!r}"
        )
    frame = objects[0]
    if not isinstance(frame, pd.DataFrame):
        raise ValueError(
            f"Objeto em {path.name} não é um DataFrame: {type(frame)!r}"
        )
    return frame


def coerce_id_columns(frame: pd.DataFrame, id_columns: tuple[str, ...]) -> pd.DataFrame:
    """Força colunas de ID para o dtype ``string`` (são códigos, não números).

    ``pyreadr`` normalmente já entrega IDs como ``object``/``str``; esta função
    torna a garantia explícita e à prova de regressão. Não toca em nenhuma outra
    coluna — a fidelidade dos tipos de origem é preservada.
    """
    present = [col for col in id_columns if col in frame.columns]
    if present:
        frame = frame.copy()
        for col in present:
            frame[col] = frame[col].astype("string")
    return frame
