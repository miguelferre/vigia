/**
 * Constantes visuales de la matriz de riesgos.
 *
 * Las etiquetas y la tabla de 25 celdas están copiadas de
 * `src/vigia/human/risk_levels.py` (fuente de verdad): si esa tabla cambia,
 * esta copia debe cambiar con ella. El backend nunca envía una celda vacía
 * (`RiskOut.level` siempre viene resuelto), así que esta copia solo sirve
 * para pintar los ejes y agregar la matriz 5x5 en el cliente (sin endpoint aparte).
 */

import type { RiskLevel, RiskMovementKind } from "@/api/types";

export const IMPACTO_LABELS: Record<number, string> = {
  1: "Insignificante",
  2: "Menor",
  3: "Moderado",
  4: "Mayor",
  5: "Severo",
};

export const PROBABILIDAD_LABELS: Record<number, string> = {
  1: "Raro",
  2: "Improbable",
  3: "Posible",
  4: "Probable",
  5: "Casi seguro",
};

/** Filas de la matriz, de Severo (arriba) a Insignificante (abajo). */
export const IMPACTOS_DESCENDENTE = [5, 4, 3, 2, 1] as const;
/** Columnas de la matriz, de Raro (izquierda) a Casi seguro (derecha). */
export const PROBABILIDADES_ASCENDENTE = [1, 2, 3, 4, 5] as const;

/** Copia de `NIVELES` de `risk_levels.py`: celda (impacto, probabilidad) -> nivel. */
export const NIVELES: Record<string, RiskLevel> = {
  "5,1": "medio", "5,2": "alto", "5,3": "alto", "5,4": "critico", "5,5": "critico",
  "4,1": "bajo", "4,2": "medio", "4,3": "alto", "4,4": "alto", "4,5": "critico",
  "3,1": "bajo", "3,2": "medio", "3,3": "medio", "3,4": "alto", "3,5": "alto",
  "2,1": "bajo", "2,2": "bajo", "2,3": "bajo", "2,4": "medio", "2,5": "medio",
  "1,1": "bajo", "1,2": "bajo", "1,3": "bajo", "1,4": "bajo", "1,5": "bajo",
};

export function nivelDeCelda(impacto: number, probabilidad: number): RiskLevel {
  return NIVELES[`${impacto},${probabilidad}`] ?? "bajo";
}

export const ETIQUETA_NIVEL: Record<RiskLevel, string> = {
  bajo: "Bajo",
  medio: "Medio",
  alto: "Alto",
  critico: "Crítico",
};

/** Orden de severidad de los cuatro niveles (subió/bajó del histórico de movimientos). */
export const ORDEN_NIVEL: Record<RiskLevel, number> = { bajo: 0, medio: 1, alto: 2, critico: 3 };

/** Token de color por nivel (`--risk-medium`; nunca un color literal). */
export const TOKEN_NIVEL: Record<RiskLevel, string> = {
  bajo: "var(--state-ok)",
  medio: "var(--risk-medium)",
  alto: "var(--state-warn)",
  critico: "var(--state-alert)",
};

/** Relleno suave de celda/chip: mismo color, 18% de opacidad sobre transparente. */
export function fondoNivel(nivel: RiskLevel): string {
  return `color-mix(in srgb, ${TOKEN_NIVEL[nivel]} 18%, transparent)`;
}

export const ESTADOS_RIESGO = ["abierto", "en_seguimiento", "cerrado"] as const;
export const ETIQUETA_ESTADO_RIESGO: Record<(typeof ESTADOS_RIESGO)[number], string> = {
  abierto: "Abierto",
  en_seguimiento: "En seguimiento",
  cerrado: "Cerrado",
};

/**
 * Sentido de un movimiento de celda, leído del `texto` compuesto por el
 * backend (spec: "nunca lo recompongas", pero el sentido de la flecha del
 * icono sí se deriva de si empieza por "subió"/"bajó"/"movido").
 */
export type SentidoMovimiento = "subio" | "bajo" | "lateral" | null;

export function sentidoDeTexto(kind: RiskMovementKind, texto: string): SentidoMovimiento {
  if (kind !== "celda") return null;
  const t = texto.toLowerCase();
  // Sin `\b` en la marca de palabra: acentuadas como "ó" no cuentan como
  // `\w` en JS y rompen el límite de palabra a mitad de "subió"/"bajó".
  if (t.includes("subió")) return "subio";
  if (t.includes("bajó")) return "bajo";
  return "lateral";
}
