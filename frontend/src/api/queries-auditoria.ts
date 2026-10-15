/**
 * Hooks de consulta de `/auditoria`: plantillas del dossier, lista de dossiers de un proyecto, detalle de
 * un dossier con sus revisiones y detalle de una revisión.
 *
 * Claves propias (frontera del carril, patrón de `queries-alertas-series.ts`):
 * `["dossiers", "plantillas"]`, `["dossiers", projectId]`,
 * `["dossiers", "detalle", id]`, `["reviews", id]`. `RAICES_POR_OBJETO`
 * (`api/queries.ts`) invalida por el prefijo
 * `"dossiers"` y `"reviews"` al llegar `dossier`/`dossier_review` por SSE.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { STALE_MS, type Opciones } from "./queries";
import type {
  Dossier,
  DossierConReviews,
  DossierPlantillas,
  DossierReviewDetalle,
  ListResponse,
} from "./types";

export const qkAuditoria = {
  plantillas: () => ["dossiers", "plantillas"] as const,
  lista: (projectId: number | null) => ["dossiers", projectId] as const,
  detalle: (dossierId: number | null) => ["dossiers", "detalle", dossierId] as const,
  revision: (reviewId: number | null) => ["reviews", reviewId] as const,
};

/** `GET /content/dossier-plantillas`: las tres plantillas traducidas. */
export function useDossierPlantillas(opciones?: Opciones<DossierPlantillas>) {
  return useQuery({
    queryKey: qkAuditoria.plantillas(),
    queryFn: () => api.get<DossierPlantillas>("/content/dossier-plantillas"),
    staleTime: Infinity,
    ...opciones,
  });
}

/** `GET /projects/{id}/dossiers`: lista paginada, orden `created_at` desc. */
export function useDossiers(projectId: number | null, opciones?: Opciones<ListResponse<Dossier>>) {
  return useQuery({
    queryKey: qkAuditoria.lista(projectId),
    queryFn: () => api.get<ListResponse<Dossier>>(`/projects/${projectId}/dossiers`),
    enabled: projectId !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

/** `GET /dossiers/{id}`: el dossier con sus revisiones embebidas. */
export function useDossier(dossierId: number | null, opciones?: Opciones<DossierConReviews>) {
  return useQuery({
    queryKey: qkAuditoria.detalle(dossierId),
    queryFn: () => api.get<DossierConReviews>(`/dossiers/${dossierId}`),
    enabled: dossierId !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

/** `GET /reviews/{id}`: hallazgos, crosswalk y bloque de reproducibilidad. */
export function useDossierReview(reviewId: number | null, opciones?: Opciones<DossierReviewDetalle>) {
  return useQuery({
    queryKey: qkAuditoria.revision(reviewId),
    queryFn: () => api.get<DossierReviewDetalle>(`/reviews/${reviewId}`),
    enabled: reviewId !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}
