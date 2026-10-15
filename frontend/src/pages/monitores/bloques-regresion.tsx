/**
 * Bloques de regresión de `/monitores/:tipo`, partidos de
 * `index.tsx` por tamaño. Cada uno se comprueba con `caps` por dentro y no
 * dibuja nada en binario ni en multiclase.
 *
 * - `RegresionArriba`: en equidad, el rango favorable (o su ausencia).
 * - `RegresionAbajo`: bajo la rejilla, el error por grupo en equidad y el
 *   error del modelo en calidad (lo que sustituye a la matriz de confusión).
 */

import type { Evaluation, MonitorType } from "@/api/types";

import { CalidadRegresion } from "./CalidadRegresion";
import { AvisoRangoFavorable, EquidadRegresion } from "./EquidadRegresion";

export interface BloquesRegresionProps {
  monitorType: MonitorType;
  evaluationId: number | null;
  projectId: number;
}

export function RegresionArriba({ monitorType, evaluationId, projectId }: BloquesRegresionProps) {
  return monitorType === "fairness" ? <AvisoRangoFavorable evaluationId={evaluationId} projectId={projectId} /> : null;
}

export function RegresionAbajo({
  monitorType,
  evaluationId,
  projectId,
  evaluaciones,
}: BloquesRegresionProps & { evaluaciones: Evaluation[] }) {
  if (monitorType === "fairness") return <EquidadRegresion evaluationId={evaluationId} projectId={projectId} />;
  if (monitorType === "quality") {
    return <CalidadRegresion evaluationId={evaluationId} projectId={projectId} evaluaciones={evaluaciones} />;
  }
  return null;
}
