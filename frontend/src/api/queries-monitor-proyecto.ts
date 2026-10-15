/**
 * Consultas propias del monitor de proyecto: derivadas de
 * `GET /projects/{id}` (`useProject`, `@/api/queries`), misma clave de
 * caché (`qk.project`), sin duplicar la petición.
 *
 * - `useVersionActiva`: la versión activa del proyecto (método del
 *   intervalo de equidad).
 * - `useAvisoLineaBase`: `aviso_linea_base` tal cual lo da
 *   el backend, nunca compuesto en el frontend.
 */

import { useProject } from "./queries";
import type { ModelVersion } from "./types";

export function useVersionActiva(projectId: number | null) {
  const consulta = useProject(projectId);
  const version: ModelVersion | null =
    consulta.data?.versions.find((v) => v.id === consulta.data?.active_version_id) ?? null;
  return { ...consulta, version };
}

/** Texto exacto del backend si la versión activa no tiene línea base
 * congelada; `null` en el resto de casos (incluida la carga). */
export function useAvisoLineaBase(projectId: number | null): string | null {
  const consulta = useProject(projectId);
  return consulta.data?.aviso_linea_base ?? null;
}
