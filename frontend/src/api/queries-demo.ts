/**
 * Guiones y reproducciones de demo (`GET/POST /demo/*`).
 * Mismo patrón que `queries-datos.ts`: los tipos de respuesta salen de
 * `schema.d.ts` vía `@/api/types`, las claves nacen aquí porque
 * `queries.ts` ya trae `qk.demoScenarios()` y `RAICES_POR_OBJETO.demo_run`
 * invalida la raíz `["demo"]` al llegar el evento SSE de la reproducción.
 *
 * Las cinco mutaciones invalidan esa misma raíz al terminar: `next` y `play`
 * antes de que el job real termine (el resultado definitivo llega por SSE,
 * como en `explicabilidad/lanzar.tsx`), y `crear`, `reiniciar` y `lab` sobre
 * una respuesta ya síncrona.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import { qk, STALE_MS, type Opciones } from "./queries";
import type { components } from "./schema";
import type { DemoRun, DemoScenario, JobResumen, ListResponse, Paginacion } from "./types";

export type CrearReproduccionBody = components["schemas"]["CreateRunBody"];
export type ReiniciarReproduccionBody = components["schemas"]["ResetRunBody"];

/** Cuerpo de `POST /demo/runs/{id}/lab`. */
export type LabRunBody = components["schemas"]["LabRunBody"];

const qkDemo = {
  runs: (p?: Paginacion) => ["demo", "runs", p ?? {}] as const,
  run: (id: number | null) => ["demo", "runs", "detalle", id] as const,
};

/** Guiones sembrados, con sus fases (`timeline_completo`, `consejeria_regional`). */
export function useGuiones(opciones?: Opciones<ListResponse<DemoScenario>>) {
  return useQuery({
    queryKey: qk.demoScenarios(),
    queryFn: () => api.get<ListResponse<DemoScenario>>("/demo/scenarios"),
    staleTime: STALE_MS,
    ...opciones,
  });
}

/** Reproducciones de demo, más recientes primero. */
export function useReproducciones(p?: Paginacion, opciones?: Opciones<ListResponse<DemoRun>>) {
  return useQuery({
    queryKey: qkDemo.runs(p),
    queryFn: () =>
      api.get<ListResponse<DemoRun>>("/demo/runs", {
        params: { offset: p?.offset ?? null, limit: p?.limit ?? null },
      }),
    staleTime: STALE_MS,
    ...opciones,
  });
}

/** Una reproducción de demo, con su `result` por fase y `matches_expected`. */
export function useReproduccion(id: number | null, opciones?: Opciones<DemoRun>) {
  return useQuery({
    queryKey: qkDemo.run(id),
    queryFn: () => api.get<DemoRun>(`/demo/runs/${id}`),
    enabled: id !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

function useInvalidarDemo() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["demo"] });
}

/** Crea el proyecto de demo y la reproducción, en estado `lista`. */
export function useCrearReproduccion() {
  const invalidar = useInvalidarDemo();
  return useMutation({
    mutationFn: (body: CrearReproduccionBody) => api.post<DemoRun>("/demo/runs", body),
    onSuccess: invalidar,
  });
}

/** Encola la siguiente fase pendiente del guion. */
export function useSiguienteFase() {
  const invalidar = useInvalidarDemo();
  return useMutation({
    mutationFn: (runId: number) => api.post<JobResumen>(`/demo/runs/${runId}/next`),
    onSuccess: invalidar,
  });
}

/** Encola todas las fases pendientes del guion, del tirón. */
export function useReproducirTodo() {
  const invalidar = useInvalidarDemo();
  return useMutation({
    mutationFn: (runId: number) => api.post<JobResumen>(`/demo/runs/${runId}/play`),
    onSuccess: invalidar,
  });
}

export interface ReiniciarReproduccionVars {
  runId: number;
  body: ReiniciarReproduccionBody;
}

/** Reinicia el proyecto de demo. Exige `confirm: true` en el cuerpo. */
export function useReiniciar() {
  const invalidar = useInvalidarDemo();
  return useMutation({
    mutationFn: ({ runId, body }: ReiniciarReproduccionVars) =>
      api.post<DemoRun>(`/demo/runs/${runId}/reset`, body),
    onSuccess: invalidar,
  });
}

export interface LaboratorioVars {
  runId: number;
  body: LabRunBody;
}

/**
 * Lanza una fase generada con parámetros a la carta sobre el proyecto de la
 * reproducción, sin avanzar `current_phase` ni `status`. Solo con la
 * capacidad `laboratorio`: la pantalla comprueba `useCan`.
 */
export function useLaboratorio() {
  const invalidar = useInvalidarDemo();
  return useMutation({
    mutationFn: ({ runId, body }: LaboratorioVars) =>
      api.post<JobResumen>(`/demo/runs/${runId}/lab`, body),
    onSuccess: invalidar,
  });
}
