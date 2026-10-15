/**
 * Lectura tolerante de `result.details` de una evaluación de calidad
 * multiclase: matriz `k x k`, tabla por clase y notas. Sin
 * React. `details` no está tipado en el OpenAPI (`result` es JSON libre): cada
 * campo se valida a mano y un campo ausente da `null`, nunca un cero.
 *
 * Las claves de clase son las de `claveClase` (`core/schema.py:clave_clase`):
 * `confusion_matrix.classes`, `por_clase` y `distribucion_etiqueta` se
 * indexan con ellas.
 */

import type { EvaluationDetail } from "@/api/types";
import { claveClase, type Clase } from "@/lib/tipo-tarea";

export interface MatrizK {
  /** Orden de filas y columnas: el de `classes` del proyecto. */
  clases: string[];
  /** `matriz[real][predicha]`: filas = clase real, columnas = clase predicha. */
  matriz: number[][];
}

export interface FilaPorClase {
  clase: string;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  soporte: number | null;
  predichas: number | null;
  tasaPredicha: number | null;
  /** Clase con menos filas que `min_group` en la ventana: sin métricas por clase. */
  insuficiente: boolean;
}

export interface DetalleCalidadMulticlase {
  matriz: MatrizK | null;
  porClase: FilaPorClase[];
  f1Ponderada: number | null;
  /** Clases que el AUC macro dejó fuera de la ventana, con su motivo. */
  aucExcluidas: { clase: string; motivo: string }[];
  /** Etiquetas reales de clases que el proyecto no declara, por clase y recuento. */
  clasesDesconocidas: { clase: string; n: number | null }[];
}

type Obj = Record<string, unknown>;

function esObjeto(v: unknown): v is Obj {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function detalles(result: EvaluationDetail["result"]): Obj | null {
  if (!esObjeto(result)) return null;
  const d = result.details;
  return esObjeto(d) ? d : null;
}

/** `details.confusion_matrix = {classes, matrix}`; `null` si falta o no es `k x k`. */
export function leerMatrizK(result: EvaluationDetail["result"]): MatrizK | null {
  const d = detalles(result);
  const cm = d?.confusion_matrix;
  if (!esObjeto(cm) || !Array.isArray(cm.classes) || !Array.isArray(cm.matrix)) return null;
  const clases = cm.classes.map((c) => claveClase(c as Clase));
  const k = clases.length;
  if (k === 0 || cm.matrix.length !== k) return null;
  const matriz: number[][] = [];
  for (const fila of cm.matrix) {
    if (!Array.isArray(fila) || fila.length !== k) return null;
    matriz.push(fila.map((x) => num(x) ?? 0));
  }
  return { clases, matriz };
}

export function leerDetalleCalidadMulticlase(result: EvaluationDetail["result"]): DetalleCalidadMulticlase {
  const d = detalles(result);
  const porClaseObj = d?.por_clase;
  const porClase: FilaPorClase[] = esObjeto(porClaseObj)
    ? Object.entries(porClaseObj).flatMap(([clase, v]) =>
        esObjeto(v)
          ? [
              {
                clase,
                precision: num(v.precision),
                recall: num(v.recall),
                f1: num(v.f1_measure),
                soporte: num(v.soporte),
                predichas: num(v.predichas),
                tasaPredicha: num(v.tasa_predicha),
                insuficiente: v.muestra_insuficiente === true,
              },
            ]
          : [],
      )
    : [];
  const excluidas = Array.isArray(d?.auc_clases_excluidas)
    ? (d!.auc_clases_excluidas as unknown[]).flatMap((e) =>
        esObjeto(e) && typeof e.clase === "string" ? [{ clase: e.clase, motivo: typeof e.motivo === "string" ? e.motivo : "" }] : [],
      )
    : [];
  const desconocidas = esObjeto(d?.clases_desconocidas)
    ? Object.entries(d!.clases_desconocidas as Obj).map(([clase, n]) => ({ clase, n: num(n) }))
    : [];
  return {
    matriz: leerMatrizK(result),
    porClase,
    f1Ponderada: num(d?.f1_ponderada),
    aucExcluidas: excluidas,
    clasesDesconocidas: desconocidas,
  };
}
