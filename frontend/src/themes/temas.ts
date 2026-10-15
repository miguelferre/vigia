/**
 * Catálogo de estéticas del build: la personal y las que registre
 * `temas-extra.ts`. Con `VITE_TEMA=miguel` solo existe la personal, no hay
 * selector de estética y quedan el modo claro y el oscuro.
 */

import { TEMAS_EXTRA } from "@/themes/temas-extra";
import type { TemaExtra } from "@/themes/temas-extra";

export const TEMA_PERSONAL: TemaExtra = {
  valor: "miguel",
  etiqueta: "Personal (pastel y oro)",
  etiquetaCorta: "Personal",
};

/**
 * Tema único: con `VITE_TEMA=<nombre>` distinto de `miguel` y `todos`, el build
 * solo trae esa estética (si `temas-extra.ts` la registra) y arranca con ella.
 */
const TEMA_BUILD = import.meta.env.VITE_TEMA;
const TEMA_UNICO =
  TEMA_BUILD && TEMA_BUILD !== "miguel" && TEMA_BUILD !== "todos"
    ? TEMAS_EXTRA.find((t) => t.valor === TEMA_BUILD)
    : undefined;

export const TEMAS_DISPONIBLES: TemaExtra[] = TEMA_UNICO
  ? [TEMA_UNICO]
  : [TEMA_PERSONAL, ...TEMAS_EXTRA];

export const TEMA_POR_DEFECTO: string = TEMAS_DISPONIBLES[0].valor;

export const HAY_SELECTOR_TEMA = TEMAS_DISPONIBLES.length > 1;

export function esTemaDisponible(valor: unknown): valor is string {
  return typeof valor === "string" && TEMAS_DISPONIBLES.some((t) => t.valor === valor);
}

export function etiquetaTema(valor: string): string {
  return TEMAS_DISPONIBLES.find((t) => t.valor === valor)?.etiquetaCorta ?? valor;
}
