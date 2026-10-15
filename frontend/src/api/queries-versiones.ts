/**
 * Comparación de versiones: `GET
 * /projects/{id}/versions/compare?a=&b=&ventana=`.
 *
 * La clave empieza por `"projects"`, así que cualquier `invalidateQueries`
 * de proyectos (activar, fijar línea base, crear versión) la refresca. Sin `a`
 * ni `b` la API resuelve la versión activa anterior y la activa (`null` = por defecto).
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { STALE_MS, type Opciones } from "./queries";
import type { components } from "./schema";

export type ComparacionVersiones = components["schemas"]["ComparacionVersiones"];
export type ComparacionFila = components["schemas"]["ComparacionFila"];
export type ComparacionLado = components["schemas"]["ComparacionLado"];
export type AlertaVivaVersion = components["schemas"]["AlertaVivaVersion"];
export type VentanaComparacion = components["schemas"]["VentanaComparacion"];

export function useComparacionVersiones(
  projectId: number | null,
  a: number | null,
  b: number | null,
  ventana: VentanaComparacion,
  opciones?: Opciones<ComparacionVersiones>,
) {
  return useQuery({
    queryKey: ["projects", "comparacion", projectId, a, b, ventana] as const,
    queryFn: () =>
      api.get<ComparacionVersiones>(`/projects/${projectId}/versions/compare`, {
        params: { a, b, ventana },
      }),
    // Sin `a` ni `b` la API resuelve la activa anterior y la activa; dos ids iguales no se comparan.
    enabled: projectId !== null && !(a !== null && a === b),
    staleTime: STALE_MS,
    ...opciones,
  });
}
