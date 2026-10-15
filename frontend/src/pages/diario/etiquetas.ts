/**
 * Etiquetas y tokens propios del diario.
 *
 * `object_type` no tiene diccionario en `src/lib/metrics.ts`; los valores
 * son los observados en la API. El color por
 * carril lo fija el encargo: humano `--chart-1`, agente `--chart-3`, modelo
 * `--chart-2`, sistema `--muted-foreground`.
 */

import type { ActorKind } from "@/api/types";

export const CARRILES: readonly ActorKind[] = ["humano", "agente", "modelo", "sistema"];

export const TOKEN_CARRIL: Record<ActorKind, string> = {
  humano: "--chart-1",
  agente: "--chart-3",
  modelo: "--chart-2",
  sistema: "--muted-foreground",
};

/** Tipos de objeto que emite el backend (valores observados en la API). */
export const TIPOS_OBJETO: readonly string[] = [
  "project",
  "model_version",
  "dataset",
  "batch",
  "monitor",
  "evaluation",
  "alert",
  "explanation",
  "job",
  "demo_run",
  "setting",
  "sistema",
];

export const ETIQUETA_OBJETO: Record<string, string> = {
  project: "Proyecto",
  model_version: "Versión",
  dataset: "Dataset",
  batch: "Lote",
  evaluation: "Evaluación",
  alert: "Alerta",
  demo_run: "Ejecución de demo",
  monitor: "Monitor",
  explanation: "Explicación",
  record: "Registro",
  job: "Trabajo",
  setting: "Ajuste",
  sistema: "Sistema",
};

export function etiquetaObjeto(tipo: string): string {
  return ETIQUETA_OBJETO[tipo] ?? tipo;
}
