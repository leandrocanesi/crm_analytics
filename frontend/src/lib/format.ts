/**
 * Formatação consistente para o painel.
 *
 * Decisão: valores monetários em USD, mas com agrupamento pt-BR
 * (ex.: US$ 4.596.039,58) — coerente com a audiência brasileira e com a
 * moeda real do dataset dunnhumby. Datas do dataset são ancoradas em
 * 2018-01-01 (NUNCA "hoje"); por isso datas são tratadas como strings do
 * backend e formatadas sem fuso para não deslocar o dia.
 */

const BRL_GROUPING_LOCALE = "pt-BR";

/** Moeda USD com agrupamento pt-BR. Ex.: 4596039.58 -> "US$ 4.596.039,58". */
export function formatCurrency(value: number, fractionDigits = 2): string {
  return new Intl.NumberFormat(BRL_GROUPING_LOCALE, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

/** Moeda USD compacta para eixos/labels. Ex.: 4596039.58 -> "US$ 4,6 mi". */
export function formatCurrencyCompact(value: number): string {
  return new Intl.NumberFormat(BRL_GROUPING_LOCALE, {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

/** Número inteiro com agrupamento pt-BR. Ex.: 155848 -> "155.848". */
export function formatNumber(value: number, fractionDigits = 0): string {
  return new Intl.NumberFormat(BRL_GROUPING_LOCALE, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

/** Número compacto. Ex.: 155848 -> "155,8 mil". */
export function formatNumberCompact(value: number): string {
  return new Intl.NumberFormat(BRL_GROUPING_LOCALE, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

/**
 * Percentual a partir de uma FRAÇÃO (0..1). Ex.: 0.47 -> "47,0%".
 * A API já entrega shares como fração, então não dividir por 100 aqui.
 */
export function formatPercent(fraction: number, fractionDigits = 1): string {
  return new Intl.NumberFormat(BRL_GROUPING_LOCALE, {
    style: "percent",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(fraction);
}

/**
 * Formata a data as-of do dataset (string ISO "YYYY-MM-DD") para exibição,
 * sem aplicar fuso horário (evita o clássico bug de "voltar um dia").
 */
export function formatAsOfDate(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!match) return isoDate;
  const [, year, month, day] = match;
  return `${day}/${month}/${year}`;
}

const MONTH_ABBR_PT = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
];

/**
 * Mês/ano abreviado a partir de ISO "YYYY-MM-01". Ex.: "2017-04-01" -> "abr/17".
 * Sem fuso (parse manual da string) para não deslocar o mês.
 */
export function formatMonthShort(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})/.exec(isoDate);
  if (!match) return isoDate;
  const year = match[1]!;
  const month = match[2]!;
  const abbr = MONTH_ABBR_PT[Number(month) - 1] ?? month;
  return `${abbr}/${year.slice(2)}`;
}

/** Mês/ano completo a partir de ISO. Ex.: "2017-04-01" -> "abr/2017". */
export function formatMonthYear(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})/.exec(isoDate);
  if (!match) return isoDate;
  const year = match[1]!;
  const month = match[2]!;
  const abbr = MONTH_ABBR_PT[Number(month) - 1] ?? month;
  return `${abbr}/${year}`;
}
