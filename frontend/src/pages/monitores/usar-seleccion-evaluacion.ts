/**
 * Selección de evaluación de `/monitores/:tipo`: lee
 * `?evaluacion=<id>` (enlazada desde el diario) una vez que la lista termina
 * de cargar y abre el detalle en el panel lateral si el id está entre las
 * cargadas, o deja un aviso breve si no. Ajuste de estado durante el render,
 * no en un efecto: react.dev/learn/you-might-not-need-an-effect
 * §"Adjusting some state when a prop changes". Partido de `index.tsx` para
 * no superar 9 KB en ese fichero.
 */

import { useState } from "react";
import { useSearchParams } from "react-router";

import type { Evaluation } from "@/api/types";

export function useSeleccionEvaluacion(evaluaciones: Evaluation[], cargando: boolean) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [evaluacionId, setEvaluacionId] = useState<number | null>(null);
  const [avisoEvaluacion, setAvisoEvaluacion] = useState<number | null>(null);
  const [parametroProcesado, setParametroProcesado] = useState<string | null | undefined>(undefined);

  const crudoParametro = searchParams.get("evaluacion");
  if (crudoParametro !== parametroProcesado && !cargando) {
    setParametroProcesado(crudoParametro);
    if (crudoParametro !== null) {
      const id = Number(crudoParametro);
      if (Number.isFinite(id)) {
        if (evaluaciones.some((e) => e.id === id)) {
          setEvaluacionId(id);
          setAvisoEvaluacion(null);
        } else {
          setAvisoEvaluacion(id);
        }
      }
    } else if (avisoEvaluacion !== null) {
      setAvisoEvaluacion(null);
    }
  }

  function seleccionarEvaluacion(id: number) {
    setEvaluacionId(id);
    setAvisoEvaluacion(null);
    setParametroProcesado(String(id));
    const siguiente = new URLSearchParams(searchParams);
    siguiente.set("evaluacion", String(id));
    setSearchParams(siguiente, { replace: true });
  }

  return {
    evaluacionId,
    avisoEvaluacion,
    seleccionarEvaluacion,
    cerrarEvaluacion: () => setEvaluacionId(null),
  };
}
