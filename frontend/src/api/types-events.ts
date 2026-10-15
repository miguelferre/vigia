/**
 * Formas de respuesta: alertas, explicabilidad, diario, trabajos, salud,
 * ajustes, demo y filtros de consulta.
 *
 * Parte de `types.ts` (que pasaba de 9 KB): reexportado desde allí sin
 * cambiar ningún nombre. Ver la nota de origen en `types-domain.ts`: todo lo
 * que viene del servidor es alias del esquema generado. Los filtros de
 * consulta (`EventFilters`, `AlertFilters`, ...) siguen a mano: son
 * parámetros de query, no respuestas, y el OpenAPI no los agrupa.
 */

import type {
  ActorKind,
  MonitorType,
  Paginacion,
  Schemas,
} from "./types-base";

/* ---------- alertas ---------- */

export type AlertHistoryEntry = Schemas["AlertHistoryEntry"];
export type Alert = Schemas["Alert"];
export type AlertAction = Schemas["AlertAction"];

/** `GET /alerts/{id}`: la alerta más su historial de acciones. */
export type AlertDetail = Schemas["AlertDetail"];

/** Entrada de `GET /alerts/catalog`. */
export type AlertCatalogItem = Schemas["AlertCatalogItem"];

/**
 * Etapa de la alerta: el último hito hecho del protocolo,
 * calculada por el backend (`services/alerting.alert_stage`). Única fuente
 * de la etiqueta en `pages/alertas/etapa.ts`.
 */
export type AlertStage = Schemas["AlertStage"];

/** Cuerpo de `POST /alerts/{id}/investigate`: hito 3. */
export type AlertInvestigateBody = Schemas["AlertInvestigateBody"];
/** Cuerpo de `POST /alerts/{id}/decide`: hito 4. */
export type AlertDecideBody = Schemas["AlertDecideBody"];
export type AlertDecisionAction = Schemas["AlertDecisionAction"];

/** `GET /projects/{id}/alerts/series`: evolución de alertas por
 * lote, día u hora para el panel del cuadro. */
export type AlertSeriesResponse = Schemas["AlertSeriesResponse"];
export type AlertSeriesItem = Schemas["AlertSeriesItem"];
export type AlertSeriesByMonitor = Schemas["AlertSeriesByMonitor"];
export type AlertSeriesBatchRef = Schemas["AlertSeriesBatchRef"];

/* ---------- explicabilidad ---------- */

export type Explanation = Schemas["Explanation"];

/* ---------- diario y trabajos ---------- */

export type Event = Schemas["Event"];

/**
 * `GET /jobs`, `GET /jobs/{id}` y `POST /jobs/{id}/cancel`: la forma completa,
 * con `params` y `cancel_requested`. Todos los campos son obligatorios (a mano
 * varios estaban marcados opcionales). Los endpoints que encolan trabajo
 * (ingesta, evaluación, explicabilidad y demo) devuelven `JobResumen`, la
 * misma forma sin esos dos campos.
 */
export type Job = Schemas["Job"];
export type JobResumen = Schemas["JobResumen"];

/* ---------- salud, ajustes y demo ---------- */

export type QueueCount = Schemas["QueueCount"];
export type Health = Schemas["Health"];
export type SettingsLlm = Schemas["SettingsLlm"];
export type Settings = Schemas["Settings"];
export type Shutdown = Schemas["Shutdown"];
export type DemoScenario = Schemas["DemoScenario"];
export type DemoRun = Schemas["DemoRun"];

/* ---------- filtros de consulta (a mano) ---------- */

export interface EventFilters extends Paginacion {
  actor_kind?: ActorKind | null;
  object_type?: string | null;
  object_id?: number | null;
  project_id?: number | null;
  since?: string | null;
  correlation_id?: string | null;
}

export interface EvaluationFilters extends Paginacion {
  monitor_type?: MonitorType | null;
  batch_id?: number | null;
}

/**
 * `GET /projects/{id}/timeline`: `monitor_type` sigue obligatorio (no
 * cambia). `metric_key` y `group_code` son listas separadas por comas
 * (`metric_key` hasta 20, ausente o vacía es 422; `group_code` ausente sigue
 * significando todos los grupos); su serialización desde arrays vive en
 * `useTimeline` (`queries-timeline.ts`), no aquí. `since`/`until` (ISO 8601)
 * filtran por la fecha de la evaluación; `until` anterior a `since` es 422.
 * No admite paginación.
 */
export interface TimelineFilters {
  monitor_type: MonitorType;
  metric_key: string;
  group_code?: string | null;
  since?: string | null;
  until?: string | null;
}

/** `status` y `severity` aceptan varios valores separados por coma. El filtro
 * por severidad lo hace el servidor;
 * una severidad desconocida es 422, no una lista vacía. */
export interface AlertFilters extends Paginacion {
  status?: string | null;
  severity?: string | null;
  /** Uno o varios `MonitorType` separados por coma; desconocido es 422. */
  monitor_type?: string | null;
}
