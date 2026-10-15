/**
 * Etiqueta y orden de la etapa de una alerta: `Alert.stage`
 * ya resume el último hito hecho del protocolo (detección, triaje,
 * investigación, decisión, seguimiento), calculado por el backend
 * (`services/alerting.alert_stage`). Antes había copias locales de un mapa
 * por `status` del motor (abierta/reconocida/en_observacion/cerrada)
 * en `AlertaPanelCabecera.tsx`, `columnas.tsx`, `detalle.tsx`, `historial.tsx`
 * y `dashboard/FilaAlertaAccion.tsx`: esta es la única fuente, sobre `stage`.
 *
 * El filtro de estado de `/alertas` (`filtros-constantes.ts`) sigue sobre
 * `status` del backend, no sobre `stage` (agrupa varias etapas a la vez);
 * sus etiquetas son vocabulario propio, documentado allí.
 */

import type { Alert, AlertDetail, AlertStage } from "@/api/types";

export const ETIQUETA_ETAPA: Record<AlertStage, string> = {
  detectada: "Detectada",
  en_observacion: "En observación",
  en_investigacion: "En investigación",
  en_seguimiento: "En seguimiento",
  cerrada: "Cerrada",
};

/**
 * Orden de progreso de las etapas, para ordenar tablas por urgencia: la
 * menos avanzada primero (nada hecho pesa más que una decisión ya tomada).
 */
export const ORDEN_ETAPA: AlertStage[] = [
  "detectada",
  "en_observacion",
  "en_investigacion",
  "en_seguimiento",
  "cerrada",
];

export function etiquetaEtapa(alerta: Pick<Alert | AlertDetail, "stage"> & { status?: string }): string {
  // Una alerta retirada (su lote se borró) no tiene etapa de protocolo.
  if (alerta.status === "retirada") return "Retirada";
  return ETIQUETA_ETAPA[alerta.stage];
}

/**
 * El motor firma el historial y los hitos como `"vigia.core <versión>"`
 * (`app/events.py:ACTOR_MODELO`): en cualquier texto visible se enseña como
 * «Vigía», nunca la cadena cruda ni el número de versión.
 */
export function actorLegible(actor: string): string {
  return actor.startsWith("vigia.core") ? "Vigía" : actor;
}

export default ETIQUETA_ETAPA;
