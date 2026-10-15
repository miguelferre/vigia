/**
 * Formato de hora de un evento del diario. Era el módulo de agrupación del
 * hilo cronológico (por día, por hora y por cadena de
 * `correlation_id`); con la línea de tiempo retirada solo queda lo
 * que sigue en uso, `horaCompleta`, que usa el panel asistente
 * (`PanelAsistente/ListaEventosAgente.tsx`).
 */

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** «hh:mm:ss» local de un evento (spec F4: hora con segundos por fila). */
export function horaCompleta(iso: string): string {
  const d = new Date(iso);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}
