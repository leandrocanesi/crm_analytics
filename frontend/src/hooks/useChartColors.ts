import { useEffect, useState } from "react";

/**
 * Lê as cores de gráfico (CSS vars hex) definidas em index.css e as reentrega
 * como strings cruas que o Recharts consegue consumir em stroke/fill/gradiente.
 *
 * Por que um hook? O Recharts aplica cor como atributo SVG, onde `var(--x)` NÃO
 * é resolvido. Então lemos os valores computados e reagimos à troca de tema
 * (classe `.dark` no <html>) via MutationObserver — assim o gráfico recolore
 * ao alternar light/dark sem recarregar.
 */
export interface ChartColors {
  revenue: string;
  accent: string;
  grid: string;
  axis: string;
  washFrom: string;
  washTo: string;
}

const VAR_NAMES: Record<keyof ChartColors, string> = {
  revenue: "--chart-revenue",
  accent: "--chart-accent",
  grid: "--chart-grid",
  axis: "--chart-axis",
  washFrom: "--chart-revenue-wash-from",
  washTo: "--chart-revenue-wash-to",
};

function readColors(): ChartColors {
  if (typeof window === "undefined") {
    return {
      revenue: "#135e57",
      accent: "#c98a2e",
      grid: "#dce8e4",
      axis: "#5e7b75",
      washFrom: "#135e5726",
      washTo: "#135e5700",
    };
  }
  const styles = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) =>
    styles.getPropertyValue(name).trim() || fallback;
  return {
    revenue: read(VAR_NAMES.revenue, "#135e57"),
    accent: read(VAR_NAMES.accent, "#c98a2e"),
    grid: read(VAR_NAMES.grid, "#dce8e4"),
    axis: read(VAR_NAMES.axis, "#5e7b75"),
    washFrom: read(VAR_NAMES.washFrom, "#135e5726"),
    washTo: read(VAR_NAMES.washTo, "#135e5700"),
  };
}

export function useChartColors(): ChartColors {
  const [colors, setColors] = useState<ChartColors>(readColors);

  useEffect(() => {
    const update = () => setColors(readColors());
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  return colors;
}
