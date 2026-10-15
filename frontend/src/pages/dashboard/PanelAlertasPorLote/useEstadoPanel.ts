/**
 * Estado del panel «Alertas por lote» en la URL (`?gran=`, `?desde=`,
 * `?hasta=`, `?tramo=`, `?rango=`). Los chips de rango
 * (24 h, 7 d, 30 d, Todo) escriben `desde` (ahora menos ese tiempo) y dejan
 * su nombre en `rango` para seguir resaltados tras recargar; el rango
 * personalizado escribe `desde`/`hasta` y quita `rango`. El navegador
 * (`Brush`) NO escribe en la URL: su ventana es estado local del componente
 * que lo pinta, para no disparar un refetch de servidor en cada arrastre.
 */

import { useSearchParams } from "react-router";

import type { SeriesGranularity } from "@/api/types";

const GRANULARIDADES: SeriesGranularity[] = ["batch", "day", "hour"];

export type Chip24h7d30dTodo = "24h" | "7d" | "30d" | "todo";

const MS_POR_CHIP: Record<Exclude<Chip24h7d30dTodo, "todo">, number> = {
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000,
};

export interface EstadoPanel {
  granularidad: SeriesGranularity;
  desde: string | null;
  hasta: string | null;
  tramo: string | null;
  /** Chip de rango resaltado; `null` cuando el rango es personalizado. */
  chipActivo: Chip24h7d30dTodo | null;
  setGranularidad: (g: SeriesGranularity) => void;
  setChip: (chip: Chip24h7d30dTodo) => void;
  setRangoPersonalizado: (desde: string | null, hasta: string | null) => void;
  setTramo: (clave: string) => void;
}

export function useEstadoPanel(): EstadoPanel {
  const [params, setParams] = useSearchParams();

  const crudoGran = params.get("gran");
  const granularidad: SeriesGranularity = GRANULARIDADES.includes(crudoGran as SeriesGranularity)
    ? (crudoGran as SeriesGranularity)
    : "batch";
  const desde = params.get("desde");
  const hasta = params.get("hasta");
  const tramo = params.get("tramo");
  const crudoRango = params.get("rango");

  function escribir(cambios: Record<string, string | null>) {
    const siguiente = new URLSearchParams(params);
    for (const [clave, valor] of Object.entries(cambios)) {
      if (valor === null) siguiente.delete(clave);
      else siguiente.set(clave, valor);
    }
    setParams(siguiente, { replace: true });
  }

  function setGranularidad(g: SeriesGranularity) {
    escribir({ gran: g === "batch" ? null : g });
  }

  function setChip(chip: Chip24h7d30dTodo) {
    if (chip === "todo") {
      escribir({ desde: null, hasta: null, rango: null });
      return;
    }
    const desdeChip = new Date(Date.now() - MS_POR_CHIP[chip]).toISOString();
    escribir({ desde: desdeChip, hasta: null, rango: chip });
  }

  function setRangoPersonalizado(nuevoDesde: string | null, nuevoHasta: string | null) {
    escribir({ desde: nuevoDesde, hasta: nuevoHasta, rango: null });
  }

  function setTramo(clave: string) {
    escribir({ tramo: tramo === clave ? null : clave });
  }

  // Chip resaltado: «Todo» sin fechas; el de `rango` si acompaña a `desde`;
  // ninguno con un rango personalizado.
  let chipActivo: Chip24h7d30dTodo | null = null;
  if (!desde && !hasta) {
    chipActivo = "todo";
  } else if (desde && !hasta && crudoRango && crudoRango in MS_POR_CHIP) {
    chipActivo = crudoRango as Chip24h7d30dTodo;
  }

  return { granularidad, desde, hasta, tramo, chipActivo, setGranularidad, setChip, setRangoPersonalizado, setTramo };
}
