/**
 * Formas de respuesta de la API por dominio.
 *
 * Parte de `types.ts` (que pasaba de 9 KB): reexportado desde allí sin
 * cambiar ningún nombre. Ya no hay tipos a mano: todos los routers declaran
 * `response_model`, el OpenAPI publica las respuestas y `schema.d.ts` las
 * genera con `npm run api:types`. Cada nombre exportado es un alias del
 * esquema generado; las diferencias con la versión a mano anterior están en
 * los comentarios de cada bloque.
 */

import type { Schemas } from "./types-base";

/* ---------- proyectos y versiones ---------- */

// `Project` ya no sale suelto en el OpenAPI: `GET /projects` devuelve
// `ProjectListItem` (Project + `summary` opcional) y el detalle
// `ProjectDetail`. El alias apunta a la fila de lista.
export type Project = Schemas["ProjectListItem"];
export type ProjectListItem = Schemas["ProjectListItem"];
export type ProjectSummary = Schemas["ProjectSummary"];
export type ModelVersion = Schemas["ModelVersion"];
export type Monitor = Schemas["Monitor"];
export type ProjectCounts = Schemas["ProjectCounts"];

/** `ProjectSummary.last_batch`: KPI de lote de la tarjeta de
 * `/cuadro` y de `/modelos`. */
export type BatchKpi = Schemas["BatchKpi"];

/** `BatchKpi.states_by_monitor`. */
export type StatesByMonitor = Schemas["StatesByMonitor"];

/** Una medida de `BatchKpi.metrics`, con su umbral ya resuelto. */
export type MetricKpi = Schemas["MetricKpi"];

/** Alertas abiertas por severidad: `ProjectSummary.alerts_open_by_severity`
 * y, por monitor, `alerts_open_by_monitor`. */
export type AlertasAbiertasPorSeveridad = Schemas["AlertasAbiertasPorSeveridad"];

/** `BatchKpi.checks_by_state[monitor]`: comprobaciones del lote por estado. */
export type ChecksPorEstado = Schemas["ChecksPorEstado"];

/** `GET/POST/PATCH /projects/{id}`. */
export type ProjectDetail = Schemas["ProjectDetail"];

/** Resumen de lote que sale dentro de `ProjectState.last_batch`. */
export type BatchResumen = Schemas["BatchResumen"];

export type MonitorEstado = Schemas["MonitorEstado"];

/** `GET /projects/{id}/state`. */
export type ProjectState = Schemas["ProjectState"];

/** `PATCH /monitors/{id}`: el monitor y el id del evento del diario. */
export type MonitorPatchResult = Schemas["MonitorPatchResult"];

/** `POST /projects/{id}/reset`. */
export type ProjectResetCounts = Schemas["ProjectResetCounts"];
export type ProjectResetResult = Schemas["ProjectResetResult"];

/* ---------- datos: datasets, lotes, registros ---------- */

/**
 * `Dataset.columns` es `DatasetColumn[] | string[] | null`: la ingesta normal
 * guarda columnas descritas y la de registros de uso solo los nombres.
 * `mapping` y `suggested_mapping` son `ColumnMappingOut`, no `ColumnMapping`
 * (el de lectura no lleva el validador del cuerpo de petición).
 */
export type Dataset = Schemas["Dataset"];
export type DatasetColumn = Schemas["DatasetColumn"];
export type PrivacyReport = Schemas["PrivacyReport"];

/** `POST /projects/{id}/datasets/upload`. */
export type DatasetUpload = Schemas["DatasetUpload"];

export type Batch = Schemas["Batch"];

/** `GET /batches/{id}/records`. En el OpenAPI es `Record`; aquí conserva el
 * guion bajo para no chocar con el `Record` de TypeScript. Trae `group_label`. */
export type Record_ = Schemas["Record"];

export type CompositionRow = Schemas["CompositionRow"];

/** Fila de totales: la misma sin `group_code` ni `group_label`. Antes era un
 * `Omit<CompositionRow, "group_code">` a mano; ahora el backend la publica. */
export type CompositionTotal = Schemas["CompositionTotal"];

/** `GET /batches/{id}/composition`. */
export type BatchComposition = Schemas["BatchComposition"];

/* ---------- evaluaciones y medidas ---------- */

export type Measurement = Schemas["Measurement"];

/** Fila de `GET /projects/{id}/evaluations` (forma ligera). */
export type Evaluation = Schemas["Evaluation"];

/** `GET /evaluations/{id}`: la ligera más el detalle. */
export type EvaluationDetail = Schemas["EvaluationDetail"];

/** Punto de `GET /projects/{id}/timeline`. */
export type TimelinePoint = Schemas["TimelinePoint"];

/* ---------- explicabilidad ---------- */

/** Resumen de explicabilidad para la tarjeta del cuadro de mando. */
export type ExplanationSummary = Schemas["ExplanationSummary"];

/* ---------- monitores: contexto de grupos ---------- */

/**
 * `Monitor.group_context`: el generador lo describe como JSON libre
 * (`Record<string, unknown> | null`, el modelo lo declara así) sin la forma
 * real que devuelve el backend cuando hay mapping. Se tipa a mano aquí en
 * vez de con `NonNullable<Monitor["group_context"]>`, que no daría los
 * campos; se estrecha con un cast en el punto de consumo.
 */
export type GroupContext = {
  protected_attr: string;
  supervised: string[];
  reference: string[];
} | null;
