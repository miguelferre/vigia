/**
 * Lógica de guardado del paso «Umbrales» (partida de `alta-umbrales.tsx`
 * para no superar 9 KB): claves de fila, umbrales actuales del monitor y
 * `PATCH /monitors/{id}` por monitor con lo editado.
 */

import { api } from "@/api/client";
import type { PropuestaUmbral, ThresholdEntryConOrigen, ThresholdsProposal } from "@/api/queries-alta";
import type { ActorBody, JsonObject, Monitor, MonitorType, ProjectDetail } from "@/api/types";
import type { EdicionUmbral } from "./alta-umbrales-fila";

export type Ediciones = Record<string, EdicionUmbral>;

export function clave(tipo: MonitorType, p: PropuestaUmbral): string {
  return `${tipo}:${p.metric_key}:${p.kind}`;
}

/** Umbrales actuales del monitor (`Monitor.thresholds.thresholds`, `core/schema.py:Threshold`). */
function thresholdsActuales(thresholds: JsonObject | null): ThresholdEntryConOrigen[] {
  const lista = thresholds && Array.isArray(thresholds.thresholds) ? thresholds.thresholds : [];
  return lista.filter(
    (t): t is ThresholdEntryConOrigen =>
      !!t &&
      typeof t === "object" &&
      typeof (t as ThresholdEntryConOrigen).metric_key === "string" &&
      typeof (t as ThresholdEntryConOrigen).value === "number",
  );
}

/**
 * Guarda en cada monitor las filas con edición (las que no tienen propuesta
 * y siguen en «mantener el actual» no se tocan). Lanza si la API rechaza algo.
 */
export async function guardarUmbralesMonitores(
  propuesta: ThresholdsProposal,
  proyecto: Pick<ProjectDetail, "monitors"> | undefined,
  ediciones: Ediciones,
  cuerpo: ActorBody,
): Promise<void> {
  for (const m of propuesta.monitors) {
    const monitor = proyecto?.monitors.find((x) => x.type === m.monitor_type);
    if (!monitor?.id) continue;
    const cambiadas = m.propuestas.filter((p) => {
      const e = ediciones[clave(m.monitor_type, p)];
      return e !== undefined && e.origen !== "fabrica";
    });
    if (cambiadas.length === 0) continue;
    const mapa = new Map(thresholdsActuales(monitor.thresholds).map((t) => [`${t.metric_key}:${t.kind}`, t]));
    for (const p of cambiadas) {
      const e = ediciones[clave(m.monitor_type, p)];
      const valor = Number(e.value);
      if (!Number.isFinite(valor)) continue;
      mapa.set(`${p.metric_key}:${p.kind}`, {
        metric_key: p.metric_key,
        kind: p.kind,
        value: valor,
        origen: e.origen,
        nota: e.origen === "linea_base" ? undefined : e.nota.trim() || undefined,
      });
    }
    await api.patch<{ monitor: Monitor; event_id: number }>(`/monitors/${monitor.id}`, {
      ...cuerpo,
      thresholds: { thresholds: Array.from(mapa.values()) },
      laboratorio: false,
    });
  }
}
