/** Tipos y utilidades compartidas entre las pantallas de `/monitores/:tipo`. */

import type { Batch, EstadoMotor, JsonObject, Measurement, MonitorType, TimelinePoint } from "@/api/types";
import { componerLote, numeroLote } from "@/lib/fases";

/**
 * Tope de peticiones de detalle por lista: la tabla de evaluaciones y el
 * violín lote a lote comparten las claves de caché.
 */
export const TOPE_DETALLE = 30;

/** `n` de la ventana de una evaluación (`evaluation.window.n`), sin pedir el detalle. */
export function nDeVentana(ventana: JsonObject | null): number | null {
  if (!ventana || typeof ventana !== "object" || Array.isArray(ventana)) return null;
  const n = (ventana as JsonObject).n;
  return typeof n === "number" ? n : null;
}

/** Origen de un umbral: sin migración, opcional en el JSON. */
export type ThresholdOrigen = "linea_base" | "fabricante" | "criterio_clinico" | "politica_organizacion" | "fabrica";

/**
 * Cómo se llama el origen `criterio_clinico` (la clave es contrato y no
 * cambia): «criterio del responsable» en todos los dominios. El parámetro
 * `_dominio` se conserva por compatibilidad con los llamadores.
 */
export function etiquetaCriterio(_dominio?: string | null, capitalizada = false): string {
  const texto = "criterio del responsable";
  return capitalizada ? texto.charAt(0).toUpperCase() + texto.slice(1) : texto;
}

export interface ThresholdEntry {
  metric_key: string;
  kind: "lower_limit" | "upper_limit";
  value: number;
  /** Ausente en un umbral de antes: se trata como "fabrica" (mismo
   * criterio que `origen_actual` de `GET /projects/{id}/thresholds/proposal`,
   * que nunca sale `None`). */
  origen?: ThresholdOrigen | null;
  nota?: string | null;
  /** Con `"prevalencia"`, `value` es una fracción de la mejora de la línea base
   * sobre la prevalencia, no un valor de la métrica; el límite resuelto llega en cada medida. */
  relativo_a?: "prevalencia" | null;
}

function esThresholdEntry(v: unknown): v is ThresholdEntry {
  if (v === null || typeof v !== "object" || Array.isArray(v)) return false;
  const o = v as JsonObject;
  return (
    typeof o.metric_key === "string" &&
    (o.kind === "lower_limit" || o.kind === "upper_limit") &&
    typeof o.value === "number"
  );
}

/** Lee `monitor.thresholds.thresholds` sin inventar claves ni orden. */
export function extraerUmbrales(thresholds: JsonObject | null): ThresholdEntry[] {
  if (!thresholds) return [];
  const lista = thresholds.thresholds;
  if (!Array.isArray(lista)) return [];
  return lista.filter(esThresholdEntry);
}

/** `metric_key` únicos de los umbrales del monitor, en orden de aparición. */
export function metricasDelMonitor(entries: ThresholdEntry[]): string[] {
  const vistas = new Set<string>();
  const resultado: string[] = [];
  for (const e of entries) {
    if (!vistas.has(e.metric_key)) {
      vistas.add(e.metric_key);
      resultado.push(e.metric_key);
    }
  }
  return resultado;
}

export interface UmbralesMetrica {
  low: number | null;
  high: number | null;
}

export function umbralesDeMetrica(entries: ThresholdEntry[], metricKey: string): UmbralesMetrica {
  let low: number | null = null;
  let high: number | null = null;
  for (const e of entries) {
    if (e.metric_key !== metricKey) continue;
    if (e.kind === "lower_limit") low = e.value;
    if (e.kind === "upper_limit") high = e.value;
  }
  return { low, high };
}

export interface OrigenLimite {
  origen: ThresholdOrigen;
  nota: string | null;
}

export interface OrigenMetrica {
  metricKey: string;
  /** Origen del límite inferior, si la métrica tiene uno configurado. */
  low: OrigenLimite | null;
  /** Origen del límite superior, si la métrica tiene uno configurado. */
  high: OrigenLimite | null;
}

/**
 * Origen y nota por métrica de los umbrales de un monitor: un
 * umbral sin `origen` guardado se trata como "fabrica", igual que hace el
 * backend en `origen_actual` de `/thresholds/proposal`. `low` y `high` se
 * guardan por separado a propósito, sin fundirlos en un origen único: una
 * métrica con dos entradas (p. ej. `label_skew`, `core/thresholds.py:50-51`)
 * puede tener un límite calibrado y el otro de fábrica sin calibrar, y
 * fundirlos tapaba ese origen "fabrica" en cuanto el otro límite tenía un
 * origen explícito 
 */
export function origenesPorMetrica(entries: ThresholdEntry[]): OrigenMetrica[] {
  const porMetrica = new Map<string, OrigenMetrica>();
  for (const e of entries) {
    const limite: OrigenLimite = { origen: e.origen ?? "fabrica", nota: e.nota ?? null };
    const actual = porMetrica.get(e.metric_key);
    if (!actual) {
      porMetrica.set(e.metric_key, {
        metricKey: e.metric_key,
        low: e.kind === "lower_limit" ? limite : null,
        high: e.kind === "upper_limit" ? limite : null,
      });
      continue;
    }
    if (e.kind === "lower_limit") actual.low = limite;
    else actual.high = limite;
  }
  return Array.from(porMetrica.values());
}

/**
 * `true` si hay algún umbral de fábrica (sin calibrar) entre las entradas
 * crudas del monitor. Se calcula sobre `extraerUmbrales`, nunca sobre
 * el resultado ya agrupado por métrica de `origenesPorMetrica`: agrupar por
 * métrica puede quedarse solo con uno de los dos límites y perder el aviso
 * obligatorio si el otro límite de esa misma métrica sigue sin calibrar.
 */
export function hayUmbralDeFabrica(entries: ThresholdEntry[]): boolean {
  return entries.some((e) => (e.origen ?? "fabrica") === "fabrica");
}

export interface DetalleFairness {
  labelWindow: JsonObject | null;
  intervalMethod: "ventanas" | "lote" | null;
}

/**
 * Método del intervalo y ventana de etiquetas de una
 * evaluación, leídos de `EvaluationDetail.result.details`
 * (`app/routers/evaluations.py::_result_podado` conserva `details` tal cual
 * en la raíz de `result`, aunque pode `measurements`, `window` y
 * `config_snapshot`) y de `EvaluationDetail.window` (el motor no siempre
 * calcula la ventana de etiquetas en un campo aparte).
 *
 * En equidad, `details.label_window` es un campo propio (solo con
 * `fairness_interval_method="ventanas"`): su sola presencia con
 * `kind==="acumulado"` ya significa "esta evaluación tuvo que juntar lotes
 * para reunir etiquetas". `intervalMethod` solo existe en equidad.
 *
 * En calidad no hay un campo aparte: la ventana propia de la evaluación
 * (`window`) es siempre de etiquetas (calidad exige etiqueta), así que su
 * `kind` es "acumulado" en el caso normal de un solo lote — eso NO es la
 * situación de etiqueta tardía y no debe pintar "Etiquetas:
 * acumuladas desde el lote N": lo distinto de la etiqueta tardía es que
 * `window.batches` reúne más de un lote (comprobado por API). Con esa condición,
 * `intervalMethod` se queda en `null` (el método del intervalo no aplica a calidad).
 */
export function detalleFairness(
  result: JsonObject | null | undefined,
  monitorType: MonitorType | null | undefined,
  window?: JsonObject | null,
): DetalleFairness {
  const vacio: DetalleFairness = { labelWindow: null, intervalMethod: null };
  if (monitorType === "fairness") {
    if (!result || typeof result !== "object" || Array.isArray(result)) return vacio;
    const details = (result as JsonObject).details;
    if (!details || typeof details !== "object" || Array.isArray(details)) return vacio;
    const metodo = (details as JsonObject).interval_method;
    const labelWindow = (details as JsonObject).label_window;
    return {
      intervalMethod: metodo === "ventanas" || metodo === "lote" ? metodo : null,
      labelWindow:
        labelWindow && typeof labelWindow === "object" && !Array.isArray(labelWindow)
          ? (labelWindow as JsonObject)
          : null,
    };
  }
  if (monitorType === "quality" && window && typeof window === "object" && !Array.isArray(window)) {
    const lotes = (window as JsonObject).batches;
    if (Array.isArray(lotes) && lotes.length > 1) {
      return { labelWindow: window as JsonObject, intervalMethod: null };
    }
  }
  return vacio;
}

export const GRUPO_GLOBAL = "global";

/** Grupos presentes en las medidas de una evaluación; `null` se etiqueta "global". */
export function gruposDeMedidas(measurements: Measurement[] | undefined): string[] {
  if (!measurements) return [];
  const vistos = new Set<string>();
  for (const m of measurements) vistos.add(m.group_code ?? GRUPO_GLOBAL);
  return Array.from(vistos).sort();
}

/** Config con solo claves de valor primitivo (número, texto o booleano). */
export type ConfigSimple = Record<string, string | number | boolean>;

export function esPrimitivo(v: unknown): v is string | number | boolean {
  return typeof v === "string" || typeof v === "number" || typeof v === "boolean";
}

/**
 * Fila editable del protocolo de un monitor: mismos seis
 * campos que `MonitorProtocolStep`/`MonitorProtocolStepBody`, con
 * `plazoDiasTexto` como texto de formulario (para poder dejarlo vacío, a
 * diferencia de un `number`) y `responsable` siempre como cadena ("" =
 * sin asignar, se guarda como `null`).
 */
export interface HitoProtocoloEdit {
  key: string;
  titulo: string;
  descripcion: string;
  entregables: string[];
  responsable: string;
  plazoDiasTexto: string;
}

/* ---------- rejilla de monitores ---------- */

/** Orden de gravedad para quedarse con el peor estado de un conjunto. */
const ORDEN_GRAVEDAD: EstadoMotor[] = ["alerta", "inestable", "aviso", "sin_datos", "ok"];

/** Puntos de `/timeline` de un grupo de una métrica, en orden cronológico. */
export interface SerieAgrupada {
  grupo: string;
  puntos: TimelinePoint[];
}

/**
 * Agrupa los puntos de `/timeline` (varias métricas y grupos en una sola
 * respuesta) por `metric_key` y, dentro, por `group_code` (`null`
 * se etiqueta `GRUPO_GLOBAL`). Cada serie queda ordenada por fecha.
 */
export function agruparPorMetrica(datos: TimelinePoint[]): Map<string, SerieAgrupada[]> {
  const porMetrica = new Map<string, Map<string, TimelinePoint[]>>();
  for (const p of datos) {
    let porGrupo = porMetrica.get(p.metric_key);
    if (!porGrupo) {
      porGrupo = new Map();
      porMetrica.set(p.metric_key, porGrupo);
    }
    const grupo = p.group_code ?? GRUPO_GLOBAL;
    const lista = porGrupo.get(grupo);
    if (lista) lista.push(p);
    else porGrupo.set(grupo, [p]);
  }
  const resultado = new Map<string, SerieAgrupada[]>();
  for (const [metrica, porGrupo] of porMetrica) {
    const series = Array.from(porGrupo.entries())
      .map(([grupo, puntos]) => ({
        grupo,
        puntos: [...puntos].sort((a, b) => a.ts.localeCompare(b.ts)),
      }))
      .sort((a, b) =>
        a.grupo === GRUPO_GLOBAL ? -1 : b.grupo === GRUPO_GLOBAL ? 1 : a.grupo.localeCompare(b.grupo),
      );
    resultado.set(metrica, series);
  }
  return resultado;
}

/** Peor estado entre el último punto de cada grupo (resumen de la tarjeta contraída). */
export function peorEstado(series: SerieAgrupada[]): EstadoMotor | null {
  let peor: EstadoMotor | null = null;
  for (const s of series) {
    const ultimo = s.puntos[s.puntos.length - 1];
    if (!ultimo) continue;
    if (peor === null || ORDEN_GRAVEDAD.indexOf(ultimo.state) < ORDEN_GRAVEDAD.indexOf(peor)) {
      peor = ultimo.state;
    }
  }
  return peor;
}

/**
 * Serie que representa la métrica en la tarjeta contraída: la global si
 * existe; si no (equidad, sin grupo global), la de peor estado.
 */
export function serieRepresentativa(series: SerieAgrupada[]): SerieAgrupada | null {
  if (series.length === 0) return null;
  const global = series.find((s) => s.grupo === GRUPO_GLOBAL);
  if (global) return global;
  return [...series].sort((a, b) => {
    const ea = a.puntos[a.puntos.length - 1]?.state ?? "sin_datos";
    const eb = b.puntos[b.puntos.length - 1]?.state ?? "sin_datos";
    return ORDEN_GRAVEDAD.indexOf(ea) - ORDEN_GRAVEDAD.indexOf(eb);
  })[0];
}

/** Último punto de cada grupo de una serie, para la hoja de métricas. */
export function ultimosPorGrupo(series: SerieAgrupada[]): { grupo: string; punto: TimelinePoint }[] {
  const filas: { grupo: string; punto: TimelinePoint }[] = [];
  for (const s of series) {
    const punto = s.puntos[s.puntos.length - 1];
    if (punto) filas.push({ grupo: s.grupo, punto });
  }
  return filas;
}

/** Una fila del eje X con el punto de cada grupo presente en esa fecha (gráfica de la tarjeta ampliada). */
export interface FilaCombinada {
  ts: string;
  porGrupo: Record<string, TimelinePoint>;
}

/** Combina varias series por grupo en filas por fecha, para una `LineChart` con una línea por grupo. */
export function combinarPorFecha(series: SerieAgrupada[]): FilaCombinada[] {
  const porTs = new Map<string, Record<string, TimelinePoint>>();
  for (const s of series) {
    for (const p of s.puntos) {
      const fila = porTs.get(p.ts) ?? {};
      fila[s.grupo] = p;
      porTs.set(p.ts, fila);
    }
  }
  return Array.from(porTs.entries())
    .map(([ts, porGrupo]) => ({ ts, porGrupo }))
    .sort((a, b) => a.ts.localeCompare(b.ts));
}

/**
 * `batch_id -> fase o "lote #N"`, con el nombre del lote detrás, para
 * mostrar la fase como dato secundario (tooltip, no eje). El número es el de
 * toda la interfaz (`numeroLote`, la línea base cuenta como 1).
 */
export function mapaFaseDeLote(batches: Batch[] | undefined): Map<number, string> {
  const mapa = new Map<number, string>();
  for (const b of batches ?? []) {
    if (b.id === null) continue;
    mapa.set(b.id, componerLote(b.phase_label ?? `lote ${numeroLote(b.seq)}`, b.dataset_name));
  }
  return mapa;
}
