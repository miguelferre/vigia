/**
 * Etiquetas en español de estados y monitores, y utilidades de formato.
 *
 * El vocabulario de métricas (`METRIC_LABELS`, `METRIC_LABELS_EXTRA` y
 * `metricLabel()`) vive en `lib/metric-labels.ts`: este fichero
 * pasaba de 9 KB al crecer el diccionario. Se reexporta aquí para que
 * ninguna pantalla tenga que cambiar su import.
 */

import type { EstadoMotor, MonitorType } from "@/api/types";

export { METRIC_LABELS, METRIC_LABELS_EXTRA, metricLabel, metricLabelPorTipo } from "@/lib/metric-labels";
export {
  esMedidaConSigno,
  esMedidaEnUnidad,
  formatoMetrica,
  formatoMetricaPartes,
  textoRangos,
  type PartesMetrica,
  type RangoFavorable,
} from "@/lib/formato-metrica";

export const ETIQUETA_ESTADO: Record<EstadoMotor, string> = {
  ok: "Correcto",
  aviso: "Aviso",
  alerta: "Alerta",
  inestable: "Inestable",
  sin_datos: "Sin datos",
};

/** Token de color de cada estado (`themes/tokens.css`), para texto y chips con texto. */
export const TOKEN_ESTADO: Record<EstadoMotor, string> = {
  ok: "--state-ok",
  aviso: "--state-warn",
  alerta: "--state-alert",
  inestable: "--state-unstable",
  sin_datos: "--state-nodata",
};

/**
 * Token de color de relleno no textual (luces, líneas superiores, series de
 * gráfica, sparklines). Solo `aviso` cambia, a
 * `--state-warn-fill`; el resto de estados vale lo mismo que `TOKEN_ESTADO`
 * porque ya cumplen 3:1 de relleno con su propio token.
 */
export const TOKEN_ESTADO_RELLENO: Record<EstadoMotor, string> = {
  ...TOKEN_ESTADO,
  aviso: "--state-warn-fill",
};

export const ETIQUETA_MONITOR: Record<MonitorType, string> = {
  fairness: "Equidad",
  quality: "Calidad",
  drift: "Deriva",
  explain: "Explicabilidad",
  cross: "Alertas cruzadas",
};

/**
 * Una línea que explica qué mide cada monitor, para tooltips y cabeceras.
 * Sin jerga del motor: el lector puede no saber qué es una alerta cruzada.
 */
export const DESCRIPCION_MONITOR: Record<MonitorType, string> = {
  fairness: "Diferencias de resultado entre grupos protegidos",
  // vale para los tres tipos (en regresión no hay «acierto», hay error).
  quality: "Acierto o error del modelo frente al valor real",
  drift: "Cambios en la distribución de los datos",
  explain: "Importancia de las variables del modelo",
  cross: "Modelo y decisiones humanas: seis reglas cruzadas",
};

/** Segmento de URL de `/monitores/:tipo` para cada tipo de monitor. */
export const RUTA_MONITOR: Record<string, MonitorType> = {
  equidad: "fairness",
  calidad: "quality",
  deriva: "drift",
};

export const MONITOR_A_RUTA: Record<string, string> = {
  fairness: "equidad",
  quality: "calidad",
  drift: "deriva",
};

/**
 * Nombres de los cuatro carriles del diario para quien no conoce Vigía
 * «Usuario», «Agente de IA», «Vigía» (lo que Vigía calcula y
 * registra sobre el modelo vigilado) y
 * «Sistema». Los valores de `actor_kind` del backend no cambian.
 */
export const ETIQUETA_CARRIL: Record<string, string> = {
  humano: "Usuario",
  agente: "Agente de IA",
  modelo: "Vigía",
  sistema: "Sistema",
};

/** Qué entra en cada carril del diario, para la leyenda y los filtros. */
export const DESCRIPCION_CARRIL: Record<string, string> = {
  humano: "Lo que hace una persona desde la interfaz: triaje, investigación y decisión de alertas, configuración, anotaciones",
  agente: "Lo que hace un agente de IA conectado por MCP o por la API",
  modelo: "Lo que Vigía calcula y registra sobre el modelo: lotes, evaluaciones, alertas y explicaciones",
  sistema: "Tareas internas: arranque, migraciones, colas y reproducción de la demo",
};

/** Formatea un número para la UI; `n/d` si no hay valor. */
export function formatoNumero(valor: number | null | undefined, decimales = 3): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "n/d";
  return valor.toLocaleString("es-ES", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });
}

/**
 * Número sin ceros de relleno: `20` en vez de `20,000`, que en español se lee
 * como veinte mil. Para umbrales, límites y valores de configuración.
 */
export function formatoCorto(valor: number | null | undefined, maxDecimales = 3): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "n/d";
  return valor.toLocaleString("es-ES", { minimumFractionDigits: 0, maximumFractionDigits: maxDecimales });
}

/** Fecha ISO del backend a `dd/mm/aaaa hh:mm`. */
export function formatoFecha(iso: string | null | undefined): string {
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
