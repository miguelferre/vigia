/**
 * Plantilla de mapeo del alta (`mapping_template` de `POST /api/projects`):
 * estado del atributo protegido y construcción del cuerpo a partir de lo que
 * el usuario eligió en el paso «Datos» (`alta-datos.tsx`).
 */

import type { MappingTemplate } from "@/api/queries-alta";
import type { ProtectedKind } from "@/api/types";
import { pareceNumerica } from "./alta-sniff";
import type { AsignacionAlta } from "./alta-roles";
import { valorDeClase } from "./clases-multiclase";
import { rangoNumerico, valorFavorable } from "./mapeo-dataset-helpers";
import type { RegresionAlta } from "./alta-regresion";

/** Atributo protegido del alta: columna, tipo y grupos, por rangos o por valores. */
export interface ProtegidoAlta {
  activo: boolean;
  col: string;
  tipo: ProtectedKind;
  unprivMin: string;
  unprivMax: string;
  privMin: string;
  privMax: string;
  unpriv: Set<string>;
  priv: Set<string>;
}

export const PROTEGIDO_VACIO: ProtegidoAlta = {
  activo: false,
  col: "",
  tipo: "categorical",
  unprivMin: "",
  unprivMax: "",
  privMin: "",
  privMax: "",
  unpriv: new Set(),
  priv: new Set(),
};

/** Al elegir la columna protegida: números con más de dos valores distintos van por rangos; el resto, por valores. */
export function protegidoConColumna(prev: ProtegidoAlta, col: string, filas: Record<string, string>[]): ProtegidoAlta {
  const tipo: ProtectedKind = col !== "" && pareceNumerica(col, filas) ? "numeric_ranges" : "categorical";
  return { ...PROTEGIDO_VACIO, activo: prev.activo, col, tipo };
}

export interface EleccionAlta extends AsignacionAlta {
  favorableLabel: string;
  variables: string[];
  protegido: ProtegidoAlta;
  /** En multiclase, las clases, el conjunto favorable y una columna de probabilidad por clase. */
  multiclase?: { clases: string[]; favorables: string[]; probabilidades: string[] };
  /** En regresión, la unidad y el rango favorable; sin valor favorable ni probabilidad. */
  regresion?: RegresionAlta;
}

export function construirPlantilla(e: EleccionAlta): MappingTemplate {
  const p = e.protegido;
  const conProtegido = p.activo && p.col !== "";
  const rangos = p.tipo === "numeric_ranges";
  const m = e.multiclase;
  const r = e.regresion;
  return {
    // Multiclase: el conjunto favorable entero, en el orden de las clases; binario, un valor.
    // Regresión: sin valor favorable (el servidor lo rechaza); el rango va en `favorable_ranges`.
    favorable_label: r
      ? null
      : m
        ? m.clases.filter((c) => m.favorables.includes(c)).map(valorDeClase)
        : (valorFavorable(e.favorableLabel) ?? ""),
    ...(r ? { target_unit: r.target_unit, favorable_ranges: r.favorable_ranges } : {}),
    ...(m
      ? {
          classes: m.clases.map(valorDeClase),
          probability_cols: m.probabilidades,
        }
      : {}),
    id_col: e.idCol.trim() || null,
    // El segundo lote hereda estas tres columnas de la plantilla.
    label_col: e.labelCol.trim() || null,
    prediction_col: e.predictionCol.trim() || null,
    probability_col: m || r ? null : e.probabilityCol.trim() || null,
    // Estable entre lotes y fuera de `feature_cols` (el backend lo rechaza si coinciden).
    timestamp_col: e.timestampCol.trim() || null,
    feature_cols: e.variables,
    protected_attr_col: conProtegido ? p.col : null,
    protected_kind: p.tipo,
    unpriv_groups: !conProtegido ? [] : rangos ? rangoNumerico(p.unprivMin, p.unprivMax) : Array.from(p.unpriv),
    priv_groups: !conProtegido ? [] : rangos ? rangoNumerico(p.privMin, p.privMax) : Array.from(p.priv),
  };
}
