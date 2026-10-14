# Procedimento de download dos dados — dunnhumby "The Complete Journey"

Os dados **não são versionados** (tamanho + termos de uso). Baixe manualmente e coloque em `data/raw/`.

## Passos
1. Acesse a página oficial de source files da dunnhumby:
   https://www.dunnhumby.com/source-files/
2. Localize o dataset **"The Complete Journey"** e faça o download (geralmente um `.zip`).
3. Aceite/observe os **termos de uso** do dataset.
4. Extraia os arquivos CSV para:
   ```
   data/raw/
   ```
5. **Não renomeie nem edite** os arquivos originais. A camada Bronze fará a ingestão fiel; qualquer limpeza acontece a partir da Silver.

## O que esperar (a confirmar por inspeção — NÃO presumir)
O pacote "The Complete Journey" normalmente inclui tabelas como transações, domicílios (demográficos), produtos, campanhas, descrições de campanha, cupons, resgates de cupom e exposição a mídia causal. **Os nomes e colunas exatos devem ser confirmados inspecionando os CSVs reais** antes de modelar (responsabilidade do `data-architect` na Fase 2). Não assuma a estrutura.

## Depois do download
Avise o maestro. Na Fase 2, o `data-architect` + `analytics-engineer` vão:
1. Inspecionar os CSVs e seus metadados.
2. Documentar o dicionário de dados (`docs/data-dictionary.md`) e o modelo (`docs/data-model.md`).
3. Construir a ingestão Bronze fiel à origem.

> Enquanto `data/raw/` estiver vazio, o pipeline não roda com dados reais — e **não** usaremos dados falsos no lugar.
