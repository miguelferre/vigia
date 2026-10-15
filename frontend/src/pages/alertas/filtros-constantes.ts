/**
 * Constantes de filtro de `alertas/index.tsx` y `Filtros.tsx`:
 * control segmentado de estado.
 */

import type { AlertSeverity } from "@/api/types";

/**
 * Filtro sobre `status` del backend (no sobre `stage`, que
 * ya no es 1:1 con `status`, porque investigar y decidir no lo tocan). El
 * chip "Abierta" (`status` en `abierta`/`reconocida`) puede cubrir cualquier
 * etapa salvo "Cerrada": Detectada, En observación (solo triaje) o En
 * investigación, y hasta En seguimiento en el caso raro de una decisión
 * registrada antes de que el motor note la recuperación de la métrica. Se
 * queda con "Abierta" (distinto de las cinco etiquetas de etapa, para no dar
 * a entender que equivale a una sola) en vez de una etiqueta nueva: sigue
 * siendo la pregunta honesta "¿el motor la considera cerrada?", no "en qué
 * hito va". El chip "En seguimiento" (`status = en_observacion`) sí es 1:1
 * con la etapa "En seguimiento" (el motor solo pasa a `en_observacion`
 * cuando la métrica ya vuelve al umbral), y "Cerrada" con "Cerrada".
 */
export type ChipEstado = "abierta" | "en_observacion" | "cerrada" | "retirada";
export const CHIPS_ESTADO: ChipEstado[] = ["abierta", "en_observacion", "cerrada", "retirada"];
export const ETIQUETA_CHIP: Record<ChipEstado, string> = {
  abierta: "Abierta",
  en_observacion: "En seguimiento",
  cerrada: "Cerrada",
  // Alertas cuyo lote de origen se borró; fuera de «Todas».
  retirada: "Retiradas",
};

/** Segmento del control de estado del artboard `Alertas`: "Todas" se
 * suma a los tres chips porque hace falta poder
 * volver a ver el conjunto completo sin desmarcar nada. */
export type SegmentoEstado = "todas" | ChipEstado;
export const SEGMENTOS_ESTADO: SegmentoEstado[] = ["todas", "abierta", "en_observacion", "cerrada", "retirada"];
export const ETIQUETA_SEGMENTO: Record<SegmentoEstado, string> = {
  todas: "Todas",
  ...ETIQUETA_CHIP,
};

// El backend solo reconoce `alta` y `media` (`SEVERIDADES_ALERTA` en
// `services/alerting.py`); un chip "Baja" aquí provocaría un 422 al viajar
// como `severity=` al servidor.
export const SEVERIDADES: AlertSeverity[] = ["alta", "media"];
