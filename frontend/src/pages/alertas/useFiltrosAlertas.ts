/**
 * Filtros, paginación y selección de la tabla de `alertas/index.tsx`
 * (artboard `Alertas`): `?estado=` y `?severidad=`
 * inicializan el control segmentado y los chips al montar, una sola vez (sin
 * `useEffect` que los siga leyendo, así que tocar los filtros después no
 * vuelve a escribir la URL con un valor viejo). El offset y la selección
 * vuelven a su estado inicial en cada cambio de filtro de servidor (ajuste
 * en el render, mismo patrón que `filtroVisto`). Aparte para que
 * `index.tsx` quede por debajo de 9 KB.
 */

import { useMemo, useState } from "react";

import type { MonitorType } from "@/api/types";
import { ESTADOS_SIN_RETIRADA, MONITORES_VALIDOS, SEGMENTO_A_ESTADOS } from "./alertas-utils";
import { SEGMENTOS_ESTADO, SEVERIDADES, type SegmentoEstado } from "./filtros-constantes";

export function useFiltrosAlertas(params: URLSearchParams, setSeleccion: (v: ReadonlySet<number>) => void) {
  const estadoInicial = params.get("estado");
  const severidadInicial = params.get("severidad");
  const [segmento, setSegmento] = useState<SegmentoEstado>(
    estadoInicial !== null && SEGMENTOS_ESTADO.includes(estadoInicial as SegmentoEstado)
      ? (estadoInicial as SegmentoEstado)
      : "todas",
  );
  const [severidades, setSeveridades] = useState<Set<string>>(
    severidadInicial !== null && SEVERIDADES.includes(severidadInicial as (typeof SEVERIDADES)[number])
      ? new Set([severidadInicial])
      : new Set(SEVERIDADES),
  );
  const monitorInicial = params.get("monitor");
  const [monitor, setMonitor] = useState<MonitorType | "todos">(
    monitorInicial !== null && MONITORES_VALIDOS.includes(monitorInicial as MonitorType)
      ? (monitorInicial as MonitorType)
      : "todos",
  );
  const [busqueda, setBusqueda] = useState("");
  const [offset, setOffset] = useState(0);

  const statusQuery = useMemo(
    () => (segmento === "todas" ? ESTADOS_SIN_RETIRADA.join(",") : SEGMENTO_A_ESTADOS[segmento].join(",")),
    [segmento],
  );
  const severityQuery = useMemo(
    () => (severidades.size === SEVERIDADES.length ? null : Array.from(severidades).join(",")),
    [severidades],
  );
  const sinSeveridades = severidades.size === 0;

  // El offset y la selección vuelven a su estado inicial en cada cambio de
  // filtro de servidor: una página o una selección de la vista anterior
  // puede no existir con los nuevos filtros.
  const filtroClave = `${statusQuery ?? ""}|${severityQuery ?? ""}`;
  const [filtroVisto, setFiltroVisto] = useState(filtroClave);
  if (filtroClave !== filtroVisto) {
    setFiltroVisto(filtroClave);
    setOffset(0);
    setSeleccion(new Set());
  }

  const alternarSeveridad = (sev: string) =>
    setSeveridades((prev) => {
      const next = new Set(prev);
      if (next.has(sev)) next.delete(sev);
      else next.add(sev);
      return next;
    });

  return {
    segmento,
    setSegmento,
    severidades,
    alternarSeveridad,
    monitor,
    setMonitor,
    busqueda,
    setBusqueda,
    offset,
    setOffset,
    statusQuery,
    severityQuery,
    sinSeveridades,
  };
}

/** Selección de filas de la tabla, para la barra de acciones en lote. */
export function useSeleccionAlertas() {
  const [seleccion, setSeleccion] = useState<ReadonlySet<number>>(new Set());

  const alternarSeleccion = (id: number) =>
    setSeleccion((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const alternarTodas = (ids: number[]) => setSeleccion((prev) => (prev.size > 0 ? new Set() : new Set(ids)));

  return { seleccion, setSeleccion, alternarSeleccion, alternarTodas };
}
