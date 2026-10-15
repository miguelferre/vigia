/**
 * Estado combinado de un monitor: el peor entre el
 * veredicto del motor (`worst_state` de la última evaluación o de
 * `states_by_monitor` del último lote) y el que se deriva de sus alertas
 * abiertas (`alerts_open_by_monitor`). Antes vivía repetido en
 * `PestanasMonitores.tsx` y `pastillas-monitor.tsx`; la tarjeta de modelo y
 * las tarjetas del cuadro lo comparten desde aquí.
 *
 * `cross` no tiene evaluación por lote: su estado sale solo de las alertas.
 */

import type { EstadoMotor } from "@/api/types";

/** Rango de gravedad para elegir el peor estado: la alerta gana. */
export const RANGO_ESTADO: Record<EstadoMotor, number> = {
  alerta: 4,
  aviso: 3,
  inestable: 2,
  sin_datos: 1,
  ok: 0,
};

export interface AlertasAbiertas {
  alta: number;
  media: number;
  baja: number;
}

/** Estado que implican las alertas abiertas: alguna alta → alerta, solo medias → aviso, ninguna → correcto. */
export function estadoDeAlertasAbiertas(abiertas: AlertasAbiertas | null | undefined): EstadoMotor {
  if (!abiertas) return "ok";
  if (abiertas.alta > 0) return "alerta";
  if (abiertas.media > 0) return "aviso";
  return "ok";
}

/** El peor de dos estados; `null` cuenta como ausencia (gana el otro). */
export function peorEstado(a: EstadoMotor | null | undefined, b: EstadoMotor | null | undefined): EstadoMotor | null {
  if (!a) return b ?? null;
  if (!b) return a;
  return RANGO_ESTADO[a] >= RANGO_ESTADO[b] ? a : b;
}

/**
 * Estado combinado de un monitor: `worst_state` del motor (null si nunca
 * evaluó) frente a sus alertas abiertas. Sin evaluación y sin alertas es
 * `sin_datos`, no `ok`: la luz gris.
 */
export function estadoMonitor(
  worstState: EstadoMotor | null | undefined,
  abiertas: AlertasAbiertas | null | undefined,
): EstadoMotor {
  const porAlertas = estadoDeAlertasAbiertas(abiertas);
  if (!worstState) return porAlertas === "ok" ? "sin_datos" : porAlertas;
  return peorEstado(worstState, porAlertas) ?? "sin_datos";
}
