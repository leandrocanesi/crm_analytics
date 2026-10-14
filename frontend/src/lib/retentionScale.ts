/**
 * Escala sequencial de UMA cor (teal) para o heatmap de coortes.
 *
 * Decisões (skill dataviz, §Sequential): magnitude = uma hue, light→dark,
 * mais ESCURO = maior retenção. O ancoramento é invertido entre temas:
 *  - light: superfície clara → piso em teal claro, topo em teal escuro;
 *  - dark:  superfície escura → piso em teal médio (ainda visível sobre o card),
 *           topo em teal claro/brilhante.
 * Em ambos os temas o piso é propositalmente destacado da superfície do card,
 * para que NENHUMA célula de dado "suma" no fundo (células ausentes é que
 * ficam vazias — isso é intencional).
 *
 * A cor é SEMPRE função da taxa (0..1), nunca do rank — regra inegociável.
 */

export type Theme = "light" | "dark";

interface Rgb {
  r: number;
  g: number;
  b: number;
}

function hexToRgb(hex: string): Rgb {
  const h = hex.replace("#", "");
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}

function rgbToHex({ r, g, b }: Rgb): string {
  const to2 = (v: number) =>
    Math.round(Math.max(0, Math.min(255, v)))
      .toString(16)
      .padStart(2, "0");
  return `#${to2(r)}${to2(g)}${to2(b)}`;
}

/** Interpolação linear em sRGB entre dois hex (ok para rampa de hue única). */
function lerpHex(a: string, b: string, t: number): string {
  const ca = hexToRgb(a);
  const cb = hexToRgb(b);
  return rgbToHex({
    r: ca.r + (cb.r - ca.r) * t,
    g: ca.g + (cb.g - ca.g) * t,
    b: ca.b + (cb.b - ca.b) * t,
  });
}

/** Luminância relativa (WCAG) para escolher texto claro/escuro sobre a célula. */
function luminance(hex: string): number {
  const { r, g, b } = hexToRgb(hex);
  const srgb = [r, g, b].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * srgb[0]! + 0.7152 * srgb[1]! + 0.0722 * srgb[2]!;
}

/** Âncoras da rampa teal por tema (piso em t=0, topo em t=1). */
const RAMP: Record<Theme, { from: string; to: string }> = {
  // teal-100 -> teal-800
  light: { from: "#C3E2DC", to: "#0A3C39" },
  // teal-600 -> teal-100 (invertido: brilha ao crescer, sobre card escuro)
  dark: { from: "#135E57", to: "#C3E2DC" },
};

const INK_DARK = "#06302E"; // texto sobre célula clara
const INK_LIGHT = "#EAF4F1"; // texto sobre célula escura

export interface CellColor {
  bg: string;
  fg: string;
}

/** Cor de fundo + texto legível para uma taxa de retenção (0..1). */
export function retentionColor(rate: number, theme: Theme): CellColor {
  const t = Math.max(0, Math.min(1, rate));
  const { from, to } = RAMP[theme];
  const bg = lerpHex(from, to, t);
  const fg = luminance(bg) > 0.45 ? INK_DARK : INK_LIGHT;
  return { bg, fg };
}

/** Paradas para a legenda (0%..100%), já resolvidas por tema. */
export function legendStops(theme: Theme, steps = 5): { rate: number; color: string }[] {
  return Array.from({ length: steps }, (_, i) => {
    const rate = i / (steps - 1);
    return { rate, color: retentionColor(rate, theme).bg };
  });
}
