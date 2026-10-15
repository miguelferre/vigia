/**
 * Utilidades, enumerados y cuerpos de petición de la API.
 *
 * Parte de `types.ts` (que pasaba de 9 KB): reexportado desde allí sin
 * cambiar ningún nombre. Ningún carril de pantalla importa de aquí
 * directamente, siempre de `@/api/types`.
 */

import type { components } from "./schema";

export type Schemas = components["schemas"];

/* ---------- utilidades ---------- */

export type JsonValue = string | number | boolean | null | JsonValue[] | { [k: string]: JsonValue };
/**
 * Objeto JSON libre. Es la misma forma que `openapi-typescript` genera para los
 * campos de JSON sin esquema (`result`, `params`, `config`, `thresholds`,
 * `window`, `before`/`after`, `extra`), así que un campo generado se pasa a
 * cualquier ayudante que lo espere sin conversión. Los valores son `unknown`:
 * hay que estrecharlos con `typeof` antes de usarlos.
 */
export type JsonObject = { [k: string]: unknown };

/** Envoltura de todas las listas paginadas de la API. */
export interface ListResponse<T> {
  items: T[];
  total: number;
}

export interface Paginacion {
  offset?: number;
  limit?: number;
}

/* ---------- enumerados (generados) ---------- */

/* Los once enumerados salen del OpenAPI como esquemas con nombre
 * (`app/schemas/respuestas_base.py`), así que son alias, no listas a mano.
 * `DatasetStatus` incluye `error` desde la enmienda. */

/** Los cinco estados del motor (`core/schema.py`). */
export type EstadoMotor = Schemas["EstadoMotor"];
export type MonitorType = Schemas["MonitorType"];
export type AlertStatus = Schemas["AlertStatus"];
export type AlertSeverity = Schemas["AlertSeverity"];
export type JobStatus = Schemas["JobStatus"];
export type JobQueue = Schemas["JobQueue"];
export type ActorKind = Schemas["ActorKind"];
export type DatasetKind = Schemas["DatasetKind"];
export type DatasetRole = Schemas["DatasetRole"];
export type DatasetStatus = Schemas["DatasetStatus"];
export type ExplanationKind = Schemas["ExplanationKind"];
/** Estado de despliegue del proyecto. */
export type DeploymentStage = Schemas["DeploymentStage"];
/** Granularidad de `GET /projects/{id}/alerts/series`. */
export type SeriesGranularity = Schemas["SeriesGranularity"];

/** Rol de la sesión: vive solo en el frontend, el backend lo recibe como texto. */
export type Rol = "gestor" | "clinico" | "auditor" | "cliente";

export const ESTADOS_MOTOR: readonly EstadoMotor[] = [
  "ok",
  "aviso",
  "alerta",
  "inestable",
  "sin_datos",
];

/* ---------- cuerpos de petición (generados) ---------- */

export type ActorBody = Schemas["ActorBody"];
export type AlertActionBody = Schemas["AlertActionBody"];
export type BaselineBody = Schemas["BaselineBody"];
export type ColumnMapping = Schemas["ColumnMapping"];
/** Mapeo tal como lo devuelve la API: sin el validador del cuerpo de petición,
 * porque el mapeo sugerido puede traer grupos vacíos. Es el tipo de lectura. */
export type ColumnMappingOut = Schemas["ColumnMappingOut"];
export type CreateRunBody = Schemas["CreateRunBody"];
export type EvaluateBody = Schemas["EvaluateBody"];
export type ExplainGlobalBody = Schemas["ExplainGlobalBody"];
export type ExplainLocalBody = Schemas["ExplainLocalBody"];
export type IngestBody = Schemas["IngestBody"];
export type MappingBody = Schemas["MappingBody"];
export type MonitorPatch = Schemas["MonitorPatch"];
export type ProjectCreate = Schemas["ProjectCreate"];
export type ProjectPatch = Schemas["ProjectPatch"];
export type ProjectResetBody = Schemas["ProjectResetBody"];
export type ProtectedKind = Schemas["ProtectedKind"];
export type ProtocolBody = Schemas["ProtocolBody"];
export type ResetRunBody = Schemas["ResetRunBody"];
export type SettingsPatchBody = Schemas["SettingsPatchBody"];
export type VersionCreate = Schemas["VersionCreate"];
export type HTTPValidationError = Schemas["HTTPValidationError"];
