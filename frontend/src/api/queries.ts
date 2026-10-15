/**
 * Claves de query y hooks compartidos.
 *
 * Todas las claves nacen aquí: el invalidador de SSE (`src/realtime/events.ts`)
 * y los carriles de pantallas usan las mismas raíces, así una invalidación por
 * prefijo alcanza a todas las consultas del recurso.
 */

import { useQuery } from "@tanstack/react-query";
import type { UseQueryOptions } from "@tanstack/react-query";

import { api } from "./client";
import type {
  Alert,
  AlertFilters,
  EvaluationFilters,
  EventFilters,
  Health,
  ListResponse,
  Monitor,
  Paginacion,
  Project,
  ProjectDetail,
  ProjectState,
  TimelineFilters,
} from "./types";

/** Segundos de frescura por defecto (10 s). */
export const STALE_MS = 10_000;

/** Tope de la API en las listas de alertas y lotes (`Query(le=500)`). */
export const LIMITE_MAX = 500;

/**
 * Filtro de alertas en dos formas: la cadena de estados separados por coma que
 * usaba antes, o el objeto con `status`, `severity` (filtro de servidor) y
 * paginación. Sin `limit`, se piden 500.
 */
export type AlertQuery = string | AlertFilters | null;

function filtrosDeAlertas(f?: AlertQuery): AlertFilters {
  if (typeof f === "string") return { status: f };
  return f ?? {};
}

/* ---------- claves ---------- */

export const qk = {
  health: () => ["health"] as const,
  settings: () => ["settings"] as const,
  projects: (p?: Paginacion) => ["projects", p ?? {}] as const,
  projectsSummary: () => ["projects", "summary"] as const,
  project: (id: number | null) => ["projects", "detalle", id] as const,
  state: (id: number | null) => ["state", id] as const,
  monitors: (id: number | null) => ["monitors", id] as const,
  monitor: (monitorId: number | null) => ["monitors", "detalle", monitorId] as const,
  alerts: (id: number | null, f?: AlertQuery) => ["alerts", id, filtrosDeAlertas(f)] as const,
  alert: (alertId: number | null) => ["alerts", "detalle", alertId] as const,
  alertCatalog: () => ["alerts", "catalogo"] as const,
  evaluations: (id: number | null, f?: EvaluationFilters) => ["evaluations", id, f ?? {}] as const,
  evaluation: (evaluationId: number | null) => ["evaluations", "detalle", evaluationId] as const,
  timeline: (id: number | null, f?: TimelineFilters) => ["timeline", id, f ?? {}] as const,
  batches: (id: number | null, p?: Paginacion) => ["batches", id, p ?? {}] as const,
  batch: (batchId: number | null) => ["batches", "detalle", batchId] as const,
  records: (batchId: number | null, p?: Paginacion & { with_features?: boolean }) =>
    ["batches", "registros", batchId, p ?? {}] as const,
  composition: (batchId: number | null) => ["batches", "composicion", batchId] as const,
  datasets: (id: number | null, p?: Paginacion) => ["datasets", id, p ?? {}] as const,
  dataset: (datasetId: number | null) => ["datasets", "detalle", datasetId] as const,
  explanations: (versionId: number | null) => ["explanations", versionId] as const,
  explanation: (explanationId: number | null) => ["explanations", "detalle", explanationId] as const,
  /** resumen de explicabilidad de la tarjeta del cuadro de
   * mando. Bajo la raíz "explanations" a propósito: la invalidación de SSE por
   * `object_type` "explanation" y "model_version" ya alcanza esa raíz. */
  explanationsSummary: (id: number | null) => ["explanations", "resumen", id] as const,
  events: (f?: EventFilters) => ["events", f ?? {}] as const,
  jobs: (status?: string | null) => ["jobs", status ?? null] as const,
  job: (jobId: number | null) => ["jobs", "detalle", jobId] as const,
  demoScenarios: () => ["demo", "escenarios"] as const,
  /** propuesta de umbrales del paso «Umbrales» del alta, `queries-alta.ts`. */
  thresholdsProposal: (id: number | null, tamanoLote: number) =>
    ["projects", "umbrales-propuesta", id, tamanoLote] as const,
  /** Prefijo de la propuesta para cualquier tamaño de lote: lo invalida quien guarda umbrales. */
  thresholdsProposalDe: (id: number | null) => ["projects", "umbrales-propuesta", id] as const,
};

/** Raíces que invalida el flujo SSE, por `object_type` del evento. */
export const RAICES_POR_OBJETO: Record<string, readonly string[]> = {
  // Claves: `object_type` tal como lo emite el backend (`record_event`, en inglés).
  project: ["projects", "state", "humana"],
  model_version: ["projects", "state", "explanations"],
  dataset: ["datasets", "projects", "humana"],
  batch: ["batches", "datasets", "projects", "state"],
  monitor: ["monitors", "state", "projects"],
  evaluation: ["evaluations", "timeline", "state", "monitors", "batches", "humana"],
  alert: ["alerts", "state", "projects"],
  explanation: ["explanations"],
  job: ["jobs"],
  demo_run: ["projects", "batches", "datasets", "state", "jobs", "demo", "humana", "risks", "dossiers"],
  setting: ["settings"],
  // las claves de `/capa-humana` nacen en `queries-humana.ts` bajo la raíz
  // "humana"; el diario de uso (`dataset`), la evaluación cruzada
  // (`evaluation`) y los outcomes (`project`) la invalidan. Dossier, revisión
  // y riesgo tienen `object_type` propio (`services/dossiers*.py`, `risks.py`).
  dossier: ["dossiers"],
  dossier_review: ["dossiers", "reviews", "jobs"],
  risk: ["risks", "alerts"],
};

/* ---------- opciones reutilizables ---------- */

export type Opciones<T> = Omit<UseQueryOptions<T, Error, T, readonly unknown[]>, "queryKey" | "queryFn">;

/* ---------- hooks base ---------- */

export function useHealth(opciones?: Opciones<Health>) {
  return useQuery({
    queryKey: qk.health(),
    queryFn: () => api.get<Health>("/health"),
    staleTime: STALE_MS,
    ...opciones,
  });
}

export function useProjects(p?: Paginacion, opciones?: Opciones<ListResponse<Project>>) {
  return useQuery({
    queryKey: qk.projects(p),
    queryFn: () => api.get<ListResponse<Project>>("/projects", { params: { ...p } }),
    staleTime: STALE_MS,
    ...opciones,
  });
}

/**
 * Rejilla de `/modelos`: una sola petición con `?summary=true`,
 * en vez de pedir el detalle fila a fila. `Project` ya es `ProjectListItem`
 * (con `summary` opcional); aquí siempre viene relleno.
 */
export function useProjectsSummary(opciones?: Opciones<ListResponse<Project>>) {
  return useQuery({
    queryKey: qk.projectsSummary(),
    queryFn: () => api.get<ListResponse<Project>>("/projects", { params: { summary: true, limit: 200 } }),
    staleTime: STALE_MS,
    ...opciones,
  });
}

export function useProject(id: number | null, opciones?: Opciones<ProjectDetail>) {
  return useQuery({
    queryKey: qk.project(id),
    queryFn: () => api.get<ProjectDetail>(`/projects/${id}`),
    enabled: id !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

export function useProjectState(id: number | null, opciones?: Opciones<ProjectState>) {
  return useQuery({
    queryKey: qk.state(id),
    queryFn: () => api.get<ProjectState>(`/projects/${id}/state`),
    enabled: id !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

export function useMonitors(id: number | null, opciones?: Opciones<ListResponse<Monitor>>) {
  return useQuery({
    queryKey: qk.monitors(id),
    queryFn: () => api.get<ListResponse<Monitor>>(`/projects/${id}/monitors`),
    enabled: id !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

/** Alertas del proyecto; el filtro admite la cadena de estados o el objeto. */
export function useAlerts(
  id: number | null,
  filtros?: AlertQuery,
  opciones?: Opciones<ListResponse<Alert>>,
) {
  const f = filtrosDeAlertas(filtros);
  return useQuery({
    queryKey: qk.alerts(id, filtros),
    queryFn: () =>
      api.get<ListResponse<Alert>>(`/projects/${id}/alerts`, {
        params: {
          status: f.status ?? null,
          severity: f.severity ?? null,
          monitor_type: f.monitor_type ?? null,
          offset: f.offset ?? null,
          limit: f.limit ?? LIMITE_MAX,
        },
      }),
    enabled: id !== null,
    staleTime: STALE_MS,
    ...opciones,
  });
}

export type { AlertFilters };

/**
 * `useTimeline`, `useBatches`, `useDatasets`, `useEvaluations`,
 * `useExplanations`, `useJobs` y `useEvents` viven en sus propios módulos
 * (partidos para no superar 9 KB por fichero). Sus claves
 * (`qk.timeline`, `qk.batches`, `qk.datasets`, `qk.evaluations`,
 * `qk.explanations`, `qk.jobs`, `qk.events`) nacen aquí arriba con las
 * demás; se reexportan para que ninguna pantalla cambie su import — todas
 * siguen importando de `@/api/queries`.
 */
export * from "./queries-timeline";
export * from "./queries-datos";
// propuesta de umbrales del paso «Umbrales» del alta.
export * from "./queries-alta";
export * from "./queries-explicabilidad";
export * from "./queries-evaluaciones";
export * from "./queries-jobs";
export * from "./queries-eventos";
