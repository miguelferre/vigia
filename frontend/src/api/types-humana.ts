/**
 * Formas de respuesta de la capa humana (deskilling, overrides, cruzadas,
 * outcomes), dossier de auditoría, matriz de riesgos y ajustes.
 *
 * Parte de `types.ts`, reexportado desde allí sin cambiar ningún nombre.
 * Todo viene del esquema generado (`npm run api:types`): aquí solo alias,
 * para que las pantallas `/capa-humana`, `/auditoria`, `/riesgos` y
 * `/ajustes` importen de `@/api/types` como las demás.
 */

import type { Schemas } from "./types-base";

/* ---------- Deskilling ---------- */

export type DeskillingResponse = Schemas["DeskillingResponse"];
export type DeskillingWindow = Schemas["DeskillingWindowOut"];
export type DeskillingTrends = Schemas["DeskillingTrendsOut"];
export type DeskillingSignal = Schemas["DeskillingSignalOut"];

/* ---------- Overrides ---------- */

export type OverridesByGroupResponse = Schemas["OverridesByGroupResponse"];
export type OverridesGroupRow = Schemas["OverridesGroupRow"];
export type OverridesByClinicianResponse = Schemas["OverridesByClinicianResponse"];
export type ClinicianDistribution = Schemas["ClinicianDistribution"];
export type OverridesClinicianList = Schemas["OverridesClinicianList"];
export type OverridesMeResponse = Schemas["OverridesMeResponse"];
export type OverridesMeWindow = Schemas["OverridesMeWindow"];
export type OverridesMeWindowStats = Schemas["OverridesMeWindowStats"];
export type OverridesMeServiceStats = Schemas["OverridesMeServiceStats"];

/* ---------- Cruzadas ---------- */

export type CrossLatest = Schemas["CrossLatestOut"];
export type CrossRule = Schemas["CrossRuleOut"];
/** Respuesta de los lanzadores en cola (`POST /cross/evaluate`, `/explain/*`). */
export type JobAccepted = Schemas["JobAccepted"];

/* ---------- Outcomes ---------- */

export type OutcomesListResponse = Schemas["OutcomesListResponse"];
export type OutcomeRow = Schemas["OutcomeRow"];
export type OutcomeSeriePunto = Schemas["OutcomeSeriePunto"];
export type OutcomeUploadResponse = Schemas["OutcomeUploadResponse"];

/* ---------- C1 registro de uso ---------- */

export type UsageLogUploadResponse = Schemas["UsageLogUploadResponse"];
export type ComprobacionCodificacion = Schemas["ComprobacionCodificacion"];
export type ValorFavorable = Schemas["ValorFavorable"];

/* ---------- Dossier ---------- */

export type Dossier = Schemas["Dossier"];
export type DossierConReviews = Schemas["DossierConReviews"];
export type DossierCreateBody = Schemas["DossierCreateBody"];
export type DossierApproach = Schemas["DossierApproach"];
export type DossierReviewCreateBody = Schemas["DossierReviewCreateBody"];
export type DossierReviewResumen = Schemas["DossierReviewResumen"];
export type DossierReviewDetalle = Schemas["DossierReviewDetalle"];
export type DossierFinding = Schemas["DossierFinding"];
export type DossierCrosswalkRef = Schemas["DossierCrosswalkRef"];
export type DossierPlantillas = Schemas["DossierPlantillas"];
export type DossierPlantillaFormulario = Schemas["DossierPlantillaFormulario"];
export type DossierPlantillaPregunta = Schemas["DossierPlantillaPregunta"];

/* ---------- Riesgos ---------- */

export type Risk = Schemas["RiskOut"];
export type RiskLevel = Schemas["RiskLevel"];
export type RiskStatus = Schemas["RiskStatus"];
export type RisksListResponse = Schemas["RisksListResponse"];
export type RiskCreateBody = Schemas["RiskCreateBody"];
export type RiskMoveBody = Schemas["RiskMoveBody"];
export type RiskCloseBody = Schemas["RiskCloseBody"];
export type RiskStatusBody = Schemas["RiskStatusBody"];
export type RiskMovementKind = Schemas["RiskMovementKind"];
export type RiskMovementTexto = Schemas["RiskMovementTexto"];
export type RiskMovementsListResponse = Schemas["RiskMovementsListResponse"];

/* ---------- Ajustes y protocolo ---------- */

// `SettingsPatchBody` y `ProtocolBody` ya salen de `types-base.ts`.
export type MonitorProtocolStep = Schemas["MonitorProtocolStep"];
export type MonitorProtocolStepBody = Schemas["MonitorProtocolStepBody"];
/** Hito del protocolo de una alerta; `key` es libre (hitos extra). */
export type ProtocolStep = Schemas["ProtocolStep"];
export type ProtocolStepStatus = Schemas["ProtocolStepStatus"];
