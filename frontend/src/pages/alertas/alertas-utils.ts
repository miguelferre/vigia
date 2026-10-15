/**
 * Constantes y funciones puras de `alertas/index.tsx`: sin estado ni JSX,
 * para que el fichero de la pantalla quede por debajo de 9 KB.
 */

import type { Alert, AlertStatus, MonitorType } from "@/api/types";
import type { ChipEstado, SegmentoEstado } from "./filtros-constantes";

/**
 * Filtro sobre `status` del backend: el chip "Abierta" cubre
 * `abierta` y `reconocida` a la vez (ver `filtros-constantes.ts`).
 */
export const SEGMENTO_A_ESTADOS: Record<ChipEstado, AlertStatus[]> = {
  abierta: ["abierta", "reconocida"],
  en_observacion: ["en_observacion"],
  cerrada: ["cerrada"],
  retirada: ["retirada"],
};
/** «Todas» no incluye las retiradas: se piden por su propio filtro. */
export const ESTADOS_SIN_RETIRADA: AlertStatus[] = ["abierta", "en_observacion", "reconocida", "cerrada"];
export const LIMITE_PAGINA = 50;
export const MONITORES_VALIDOS: MonitorType[] = ["fairness", "quality", "drift", "explain", "cross"];

/** Recuento de alertas por segmento de estado, para los números del control segmentado. */
export function contarPorSegmento(items: Alert[]): Record<SegmentoEstado, number> {
  const conteo: Record<SegmentoEstado, number> = {
    todas: items.filter((i) => i.status !== "retirada").length,
    abierta: 0,
    en_observacion: 0,
    cerrada: 0,
    retirada: 0,
  };
  for (const item of items) {
    (Object.keys(SEGMENTO_A_ESTADOS) as ChipEstado[]).forEach((seg) => {
      if ((SEGMENTO_A_ESTADOS[seg] as string[]).includes(item.status)) conteo[seg] += 1;
    });
  }
  return conteo;
}

export function esRetirada(alerta: Pick<Alert, "status">): boolean {
  return alerta.status === "retirada";
}

/** Filtro de texto sobre título y clave de métrica, sin distinguir mayúsculas ni acentos. */
export function normaliza(s: string): string {
  return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

/** Descarga en el cliente, sin red: el usuario ya tiene acceso a estos datos en pantalla, esto solo se los guarda como fichero. */
export function exportarAlertas(alertas: Alert[], projectId: number): void {
  const blob = new Blob([JSON.stringify(alertas, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `alertas-proyecto-${projectId}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

/** Recuento de severidad y última actualización de las filas en vista, para la barra bajo la tabla. */
export function resumenFilas(filas: Alert[]): { ultimaActualizacion: string | null; porSeveridad: Record<string, number> } {
  const ultimaActualizacion = filas.reduce<string | null>(
    (acc, a) => (acc === null || a.updated_at > acc ? a.updated_at : acc),
    null,
  );
  const porSeveridad = { alta: 0, media: 0 } as Record<string, number>;
  filas.forEach((a) => {
    if (a.severity in porSeveridad) porSeveridad[a.severity] += 1;
  });
  return { ultimaActualizacion, porSeveridad };
}
