/**
 * Formato español de fechas y resolución de periodos relativos.
 *
 * `formatoFecha` de `lib/metrics.ts` no se toca ni se mueve aquí (lo usan ya
 * varias pantallas); este módulo es el sitio nuevo para `SelectorPeriodo` y
 * para quien necesite el formato corto (sin hora).
 */

/** Fecha ISO a `dd/mm/aaaa`. "n/d" si no hay valor o la fecha no es válida. */
export function formatoFechaCorta(iso: string | null | undefined): string {
  if (!iso) return "n/d";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** Fecha ISO a `dd/mm/aaaa hh:mm`. Mismo criterio que `formatoFecha` de `lib/metrics.ts`. */
export function formatoFechaLarga(iso: string | null | undefined): string {
  if (!iso) return "n/d";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const UNIDADES_RELATIVO: ReadonlyArray<{ limite: number; divisor: number; unidad: Intl.RelativeTimeFormatUnit }> = [
  { limite: 60, divisor: 1, unidad: "second" },
  { limite: 3600, divisor: 60, unidad: "minute" },
  { limite: 86400, divisor: 3600, unidad: "hour" },
  { limite: 2592000, divisor: 86400, unidad: "day" },
  { limite: 31536000, divisor: 2592000, unidad: "month" },
];

const FORMATO_RELATIVO = new Intl.RelativeTimeFormat("es-ES", { numeric: "auto", style: "short" });

/**
 * Fecha ISO a tiempo relativo corto («hace 3 min», «hace 2 h», «hace 5 d»).
 * Usa `PageHeader`'s `marcaTiempo` y quien necesite un texto breve junto al
 * icono de reloj; la fecha completa va en el `title` con `formatoFechaLarga`.
 */
export function formatoRelativo(iso: string | null | undefined): string {
  if (!iso) return "n/d";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const segundos = Math.round((d.getTime() - Date.now()) / 1000);
  const abs = Math.abs(segundos);
  for (const { limite, divisor, unidad } of UNIDADES_RELATIVO) {
    if (abs < limite) return FORMATO_RELATIVO.format(Math.round(segundos / divisor), unidad);
  }
  return FORMATO_RELATIVO.format(Math.round(segundos / 31536000), "year");
}

/** Cuánto abarca una serie, y por tanto qué parte de la fecha distingue sus puntos. */
export type EscalaEje = "segundo" | "hora" | "dia" | "fecha";

/** Etiqueta de una marca del eje X según la escala de `escalaDeFechas`. */
export function formatoEje(iso: string | null | undefined, escala: EscalaEje): string {
  if (!iso) return "n/d";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  if (escala === "segundo") {
    return d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  if (escala === "hora") {
    return d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
  }
  if (escala === "dia") {
    return d.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit" });
  }
  return d.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

/**
 * Decide la escala del eje X mirando lo que abarca la serie.
 *
 * Con un formato fijo el eje puede quedarse mudo: una tirada de demo mete las
 * nueve evaluaciones en el mismo minuto, así que `dd/mm/aaaa` repite la misma
 * fecha nueve veces y `hh:mm` repite la misma hora. La regla es elegir la
 * unidad más gruesa que todavía distinga los puntos, sin mentir: dos años
 * distintos siempre llevan el año, aunque `dd/mm` bastara para separarlos.
 *
 * Si ni los segundos separan los puntos (varias evaluaciones dentro del mismo
 * segundo) se queda en `segundo`: el dato que de verdad los distingue es la
 * fase del lote, y esa va en el tooltip.
 */
export function escalaDeFechas(isos: readonly string[]): EscalaEje {
  const fechas: Date[] = [];
  const dias = new Set<string>();
  const anios = new Set<number>();
  for (const iso of isos) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) continue;
    fechas.push(d);
    dias.add(d.toDateString());
    anios.add(d.getFullYear());
  }
  if (fechas.length === 0) return "dia";
  if (anios.size > 1) return "fecha";
  if (dias.size > 1) return "dia";
  const distintas = (escala: EscalaEje) =>
    new Set(fechas.map((d) => formatoEje(d.toISOString(), escala))).size;
  return distintas("hora") === fechas.length ? "hora" : "segundo";
}

export type Periodo = "dia" | "semana" | "mes" | "trimestre" | "anio" | "personalizado";

/** Opciones del selector, en el orden en que se muestran. */
export const OPCIONES_PERIODO: ReadonlyArray<{ value: Periodo; label: string }> = [
  { value: "dia", label: "Último día" },
  { value: "semana", label: "Última semana" },
  { value: "mes", label: "Último mes" },
  { value: "trimestre", label: "Último trimestre" },
  { value: "anio", label: "Último año" },
  { value: "personalizado", label: "Personalizado" },
];

export interface RangoFechas {
  since?: string;
  until?: string;
}

/** Fechas `aaaa-mm-dd` de los campos del periodo "personalizado". */
export interface RangoPersonalizado {
  since?: string;
  until?: string;
}

/**
 * Resuelve un periodo a su rango en ISO 8601, en hora local.
 *
 * Los periodos fijos son ventanas relativas: `until` es el momento actual y
 * `since` se calcula hacia atrás desde ahí. "Mes" y "trimestre" restan meses
 * naturales, no 30/90 días fijos (del 31 de marzo, restar un mes cae a fin de
 * febrero, como el calendario); se elige así salvo que aparezca un motivo en
 * contra para preferir una ventana de días fija.
 *
 * "Personalizado" toma las fechas `aaaa-mm-dd` del selector tal cual, en hora
 * local: `since` a las 00:00:00 y `until` a las 23:59:59,999, para no perder
 * por el desfase de `new Date("aaaa-mm-dd")` (que se interpreta en UTC) los
 * eventos del propio día del rango, igual que hace el filtro "Desde" de
 * `pages/diario/index.tsx`.
 */
export function resolverPeriodo(periodo: Periodo, personalizado?: RangoPersonalizado): RangoFechas {
  if (periodo === "personalizado") {
    const since = personalizado?.since ? new Date(`${personalizado.since}T00:00:00`) : null;
    const until = personalizado?.until ? new Date(`${personalizado.until}T23:59:59.999`) : null;
    return {
      since: since && !Number.isNaN(since.getTime()) ? since.toISOString() : undefined,
      until: until && !Number.isNaN(until.getTime()) ? until.toISOString() : undefined,
    };
  }

  const hasta = new Date();
  const desde = new Date(hasta);
  switch (periodo) {
    case "dia":
      desde.setDate(desde.getDate() - 1);
      break;
    case "semana":
      desde.setDate(desde.getDate() - 7);
      break;
    case "mes":
      desde.setMonth(desde.getMonth() - 1);
      break;
    case "trimestre":
      desde.setMonth(desde.getMonth() - 3);
      break;
    case "anio":
      desde.setFullYear(desde.getFullYear() - 1);
      break;
  }
  return { since: desde.toISOString(), until: hasta.toISOString() };
}
