/**
 * Tipos locales sobre `DemoRun.result` y alias de la fase de guion.
 * `DemoScenario.phases` ya viene tipado del OpenAPI
 * (`DemoScenarioPhase`, con `lab_params`): aquí solo se le da nombre.
 * `result` sigue siendo `{[key: string]: unknown}[]` en el esquema (lista de
 * dicts heterogéneos, `demo_player.py::next_phase`), así que se afina a lo
 * que el reproductor escribe de verdad, mismo patrón que `job.result` en
 * `explicabilidad/lanzar.tsx`.
 */

import type { DemoRun, DemoScenario, EstadoMotor } from "@/api/types";

/** Una fase del guion tal como la sirve `GET /demo/scenarios`. */
export type FaseGuion = NonNullable<DemoScenario["phases"]>[number];

/** Resumen de una fase ya reproducida (`next_phase`/`play`; `adoptado` cuando la línea base la subió el usuario). */
export interface FaseResumen {
  phase_key: string;
  batch_id: number;
  states: Partial<Record<string, EstadoMotor>>;
  expected: Record<string, string>;
  matches_expected: Record<string, boolean>;
  explain_calculado: boolean;
  adoptado?: boolean;
}

/** `result` de una reproducción, tipado, en el orden en que se reprodujeron las fases. */
export function fasesReproducidas(run: DemoRun | null | undefined): FaseResumen[] {
  return (run?.result ?? []) as unknown as FaseResumen[];
}

/** `DemoRun.status`: `"lista" | "en_curso" | "terminada"` (`demo_player.py`). */
export const ETIQUETA_ESTADO_RUN: Record<string, string> = {
  lista: "Lista para empezar",
  en_curso: "En curso",
  terminada: "Terminada",
};
