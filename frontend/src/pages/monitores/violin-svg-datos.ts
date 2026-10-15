/**
 * Helpers de presentación del violín «lote a lote» sin JSX (color de PSI,
 * etiqueta de fase abreviada): partidos de `violin-svg.tsx` (≤ 9 KB) al añadir el indicador de desbordamiento y
 * la etiqueta abreviada bajo 72 px de hueco.
 */

import { colorEstado } from "@/components/vigia/StateBadge";
import type { ViolinPreparado } from "./violin-lote-a-lote-datos";

/** Color del texto de PSI bajo un lote, según la lectura ya calculada (glosario). */
export function colorPsi(v: ViolinPreparado): string {
  if (v.lectura === "cambio fuerte") return colorEstado("alerta", "texto");
  if (v.lectura === "cambio moderado") return colorEstado("aviso", "texto");
  return "var(--muted-foreground)";
}

/**
 * Etiqueta de fase abreviada bajo 72 px de hueco: antes se
 * ocultaba entera; con `HUECO_MIN` de 44 px siempre hay sitio para unos
 * pocos caracteres (~1 cada 6 px, mínimo 3), así que se acorta con puntos
 * suspensivos en vez de desaparecer. El texto completo va en un `<title>`.
 */
export function etiquetaFaseCorta(fase: string, hueco: number): string {
  const maxCaracteres = Math.max(3, Math.floor(hueco / 6));
  if (fase.length <= maxCaracteres) return fase;
  return `${fase.slice(0, maxCaracteres - 1)}…`;
}
