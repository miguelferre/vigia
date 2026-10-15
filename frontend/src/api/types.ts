/**
 * Alias cómodos sobre los tipos de la API.
 *
 * Peticiones y respuestas vienen de `schema.d.ts`, generado con
 * `npm run api:types` desde `docs/api/openapi.json`. Ya no hay tipos de
 * respuesta escritos a mano: todos los routers declaran `response_model`
 * (`app/schemas/respuestas_*.py`, con `extra="forbid"`), así que el OpenAPI
 * publica cada respuesta y `types-domain.ts` (proyectos, versiones, monitores,
 * datos, evaluaciones) y `types-events.ts` (alertas, explicabilidad, diario,
 * trabajos, salud, ajustes y demo) solo declaran alias.
 *
 * Regla: después de cualquier cambio del backend que toque un serializador o
 * un `response_model`, hay que regenerar el OpenAPI
 * (`vigia export openapi --out docs/api/openapi.json`) y los tipos
 * (`cd frontend && npm run api:types`). `tests/api/test_contrato.py` falla si
 * un serializador devuelve una clave que el modelo no declara.
 *
 * Lo único a mano son los filtros de consulta de `types-events.ts`
 * (parámetros de query, no respuestas), `Rol` y las utilidades `JsonValue`,
 * `JsonObject`, `ListResponse` y `Paginacion` de `types-base.ts`.
 *
 * Este fichero es solo el punto de entrada: ningún carril de pantalla importa
 * de `types-base`, `types-domain` ni `types-events` directamente, siempre de
 * `@/api/types`. Partido en tres módulos para no superar 9 KB por fichero;
 * ningún nombre exportado cambia al mover.
 */

export * from "./types-base";
export * from "./types-domain";
export * from "./types-events";
// Capa humana, dossier, riesgos, ajustes y protocolo: alias en su propio
// módulo para no pasar de 9 KB; mismo punto de entrada.
export * from "./types-humana";

import type { AlertSeverity, MonitorType } from "./types-base";
import type { CompositionRow, Project, Record_, TimelinePoint } from "./types-domain";
import type { Alert, Event } from "./types-events";

/* ---------- contrato en tiempo de compilación ---------- */

/** Igualdad estricta de tipos: distingue `number | null` de `number`. */
type Igual<A, B> =
  (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;

/** Solo acepta `true`: si la comprobación falla, `tsc` para aquí. */
type Exigir<T extends true> = T;

/**
 * Campos clave que el esquema generado no puede perder. Si el backend deja de
 * publicar uno (o le cambia la nulabilidad), indexarlo es un error de tipo y
 * `npx tsc -b` falla en este fichero en lugar de romper una pantalla en
 * tiempo de ejecución. Ninguna de estas líneas emite código.
 */
export type ContratoApi = {
  "Project.id": Exigir<Igual<Project["id"], number | null>>;
  "Alert.severity": Exigir<Igual<Alert["severity"], AlertSeverity>>;
  "Alert.monitor_type": Exigir<Igual<Alert["monitor_type"], MonitorType>>;
  "Event.after": Exigir<Igual<Event["after"], { [k: string]: unknown } | null>>;
  "TimelinePoint.threshold_low": Exigir<Igual<TimelinePoint["threshold_low"], number | null>>;
  "CompositionRow.group_label": Exigir<Igual<CompositionRow["group_label"], string | null>>;
  "Record.group_label": Exigir<Igual<Record_["group_label"], string | null>>;
};
