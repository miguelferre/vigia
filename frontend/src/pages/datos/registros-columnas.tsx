/**
 * Columnas de predicción y etiqueta de `registros.tsx` según lo que da el
 * modelo: una probabilidad (binaria), `k` probabilidades
 * (multiclase) o un valor continuo (regresión). Decide `caps.probabilidad`,
 * no el tipo suelto. Partido de `registros.tsx` por tamaño.
 */

import type { Record_ } from "@/api/types";
import type { LegacyColumnDef } from "@/components/vigia";
import type { EstadoTipoTarea } from "@/hooks/useTipoTarea";
import { formatoNumero } from "@/lib/metrics";
import { claveClase } from "@/lib/tipo-tarea";

import { ProbabilidadesClases } from "./registros-probabilidades";

type Columnas = LegacyColumnDef<Record_, unknown>[];

/** Cifra continua (sin unidad: va en la cabecera) con los mismos 2 decimales en toda la columna. */
function cifra(valor: number | null | undefined, conSigno = false): string {
  if (valor == null || !Number.isFinite(valor)) return "n/d";
  return valor.toLocaleString("es-ES", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    signDisplay: conSigno ? "exceptZero" : "auto",
  });
}

function conUnidad(titulo: string, unidad: string | null): string {
  return unidad ? `${titulo} (${unidad})` : titulo;
}

/** Regresión: valor predicho, valor real y error con signo; con rango, además si la predicción cae dentro. */
function columnasRegresion(tarea: EstadoTipoTarea): Columnas {
  const { unidad, rangos } = tarea;
  const columnas: Columnas = [
    {
      id: "prediccion_valor",
      header: conUnidad("Predicción", unidad),
      cell: ({ row }) => cifra(row.original.prediction_value),
    },
    {
      id: "etiqueta_valor",
      header: conUnidad("Valor real", unidad),
      cell: ({ row }) => (row.original.label_value == null ? "—" : cifra(row.original.label_value)),
    },
    {
      id: "error_valor",
      header: conUnidad("Error: predicción menos real", unidad),
      cell: ({ row }) => {
        const { prediction_value: p, label_value: r } = row.original;
        return p == null || r == null ? "—" : cifra(p - r, true);
      },
    },
  ];
  if (rangos.length > 0) {
    columnas.push({
      id: "en_rango",
      header: "Predicción dentro del rango",
      cell: ({ row }) => (row.original.prediction === 1 ? "Sí" : "No"),
    });
  }
  return columnas;
}

function columnasBinaria(): Columnas {
  return [
    { header: "Predicción", accessorKey: "prediction" },
    { id: "prob", header: "Prob. favorable", cell: ({ row }) => formatoNumero(row.original.prob_favorable, 3) },
    { header: "Etiqueta", accessorKey: "label" },
  ];
}

function columnasMulticlase(tarea: EstadoTipoTarea): Columnas {
  return [
    { id: "prediccion_clase", header: "Predicción", cell: ({ row }) => row.original.prediction_class ?? "—" },
    {
      id: "prob_clase_predicha",
      header: "Prob. de la clase predicha",
      cell: ({ row }) => {
        const probs = row.original.probabilities;
        const i = tarea.clases.indexOf(claveClase(row.original.prediction_class ?? ""));
        return probs && i >= 0 ? formatoNumero(probs[i], 3) : "—";
      },
    },
    {
      id: "probabilidades",
      header: "Probabilidad por clase",
      cell: ({ row }) => <ProbabilidadesClases probs={row.original.probabilities} clases={tarea.clases} />,
    },
    { id: "etiqueta_clase", header: "Etiqueta", cell: ({ row }) => row.original.label_class ?? "—" },
  ];
}

/**
 * Columnas de predicción, probabilidad y etiqueta. Sin `caps` (sin proyecto)
 * cae a la forma de siempre; mientras el proyecto carga, `registros.tsx` no
 * llega aquí.
 */
export function columnasPrediccion(tarea: EstadoTipoTarea): Columnas {
  const salida = tarea.caps?.probabilidad;
  switch (salida) {
    case "vector":
      return columnasMulticlase(tarea);
    case null:
      return columnasRegresion(tarea);
    case "escalar":
    case undefined:
      return columnasBinaria();
    default: {
      const _exhaustivo: never = salida;
      throw new Error(`salida del modelo no reconocida: ${String(_exhaustivo)}`);
    }
  }
}
