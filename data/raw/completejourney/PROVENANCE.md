# Proveniência — completejourney (84.51°)

Arquivos originais **intocados**, baixados em 2026-10-14.

- **Fonte**: pacote R `completejourney` (Bradley Boehmke / Steven Mortimer).
  Repositório: https://github.com/bradleyboehmke/completejourney
  Download direto (sem login): `https://github.com/bradleyboehmke/completejourney/raw/master/data/<arquivo>`
- **Origem dos dados**: 84.51° — *The Complete Journey* Customer Journey study (http://www.8451.com/area51/). 84.51° é o braço de ciência de dados da dunnhumby nos EUA.
- **Licença/termos**: uso acadêmico/educacional conforme o pacote `completejourney` (GPL-3 no código; dados do estudo 84.51°).

## ⚠️ Distinção importante (regras nº 1 e nº 2 do CLAUDE.md)
Esta **não é** a release original "The Complete Journey" da dunnhumby referenciada originalmente em `docs/download-data.md`. É o **re-lançamento do 84.51° do mesmo estudo**, com diferenças:
- **~2.469 domicílios / ~1 ano** (a original dunnhumby: 2.500 domicílios / 2 anos).
- **Schema "tidy"** com colunas renomeadas em inglês (ex.: `household_id`, `basket_id`) — difere dos nomes crus da dunnhumby (`HOUSEHOLD_KEY`, `BASKET_ID`, `DAY`).
- Formato de distribuição **`.rds` / `.rda`** (binário R), não CSV.

O dicionário de dados (`docs/data-dictionary.md`) e o modelo (`docs/data-model.md`) devem refletir **o schema real do 84.51°**, confirmado por inspeção — nunca presumido.

## Formato
- `.rds` — um único objeto R serializado (tabelas grandes: `transactions`, `promotions`).
- `.rda` — objeto(s) R nomeados (tabelas menores).
- Leitura em Python via `pyreadr`. A conversão para formato tabular/Parquet é o **primeiro passo da camada Bronze**, não acontece aqui.

Checksums em `SHA256SUMS.txt`.
