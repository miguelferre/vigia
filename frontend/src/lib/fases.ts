/**
 * Traducción de `Batch.phase_label` para pantallas que lo enseñan.
 *
 * `phase_label` es texto libre en ingesta real (`datos/index.tsx:58-59` del
 * formulario de subida): un valor que no encaja en el mapa se deja tal cual,
 * nunca se oculta ni se rompe. Las claves reconocidas son las que escribe el
 * guion de la demo (`sim/scenarios.py`, `demo_player.py:703` para `lab:`).
 *
 * Único traductor del repo: `pages/modelos/etiquetas.ts` y
 * `pages/monitores/etiquetas.ts` reexportan desde aquí.
 */

/**
 * Etiquetas de fase del guion de la demo (`fases` de `GET /content/demo`):
 * clave de fase (`b1`, `e1_evento`, `e1_recovery`, `lab:*`) a
 * etiqueta y descripción en español. Las registra `useGuionDemo()`
 * (`api/queries-contenido.ts`) al cargar el contenido; hasta entonces
 * `etiquetaLote` cae a la regex de siempre.
 */
export interface FaseDemo {
  etiqueta: string;
  descripcion: string;
}

let fasesDemo: Readonly<Record<string, FaseDemo>> = {};

export function registrarFasesDemo(fases: Readonly<Record<string, FaseDemo>>): void {
  fasesDemo = fases;
}

/** Las fases registradas (vacío hasta que llega el contenido). */
export function fasesDemoRegistradas(): Readonly<Record<string, FaseDemo>> {
  return fasesDemo;
}

const RE_LINEA_BASE = /^b([1-5])$/;
const RE_EVENTO = /^e(\d+)_evento$/;
const RE_RECOVERY = /^e(\d+)_recovery$/;

/**
 * `timeline_completo` reutiliza los mismos `b1..b5`, `e1_evento`
 * y `e1_recovery` que `caso_digestivo` (`sim/scenarios.py`), así que ya
 * llegan etiquetados por `fasesDemoRegistradas()`. Su evento y recovery de
 * escenario 2 (`e2_evento`, `e2_recovery`) no los cubre ningún guion con
 * contenido propio y caían en la regex genérica («Evento 2»). Texto tomado
 * de los títulos de `sim/scenarios.py` (`_E2_EVENTO`, `_E2_RECOVERY`).
 */
const FASES_SIN_CONTENIDO: Readonly<Record<string, string>> = {
  e2_evento: "Protocolo nuevo",
  e2_recovery: "Tras el protocolo nuevo",
};

/**
 * Traduce una clave de fase (`Batch.phase_label`). Orden: 1) clave
 * exacta en `fasesDemoRegistradas()` (`b1`, `e1_evento`, `e1_recovery` →
 * «Línea base», «Casos nuevos», «Tras las medidas», las etiqueta el
 * contenido del guion `caso_digestivo`, no este fichero); 2) `lab:<fase>` →
 * «Laboratorio: <etiqueta de esa fase>» sea cual sea el origen de la
 * etiqueta; 3) si el contenido no ha llegado todavía (`useGuionDemo()` lo
 * registra al cargar `GET /content/demo`), la regex de siempre como
 * respaldo; 4) un `phase_label` libre (ingesta real) se devuelve tal cual.
 * Quien pinte antes del primer render con contenido ve el respaldo hasta
 * que React repinte con `fasesDemoRegistradas()` ya poblado.
 */
export function etiquetaLote(phaseLabel: string | null | undefined): string | null {
  if (!phaseLabel) return phaseLabel ?? null;
  if (phaseLabel.startsWith("lab:")) {
    const resto = phaseLabel.slice(4);
    return `Laboratorio: ${etiquetaLote(resto) ?? resto}`;
  }
  const registrada = fasesDemoRegistradas()[phaseLabel];
  if (registrada) return registrada.etiqueta;
  const sinContenido = FASES_SIN_CONTENIDO[phaseLabel];
  if (sinContenido) return sinContenido;
  const base = RE_LINEA_BASE.exec(phaseLabel);
  if (base) return `Línea base ${base[1]}`;
  const evento = RE_EVENTO.exec(phaseLabel);
  if (evento) return `Evento ${evento[1]}`;
  const recuperacion = RE_RECOVERY.exec(phaseLabel);
  if (recuperacion) return `Recuperación ${recuperacion[1]}`;
  return phaseLabel;
}

/**
 * Número de lote que ve el usuario: `Batch.seq` empieza en 0 y la interfaz
 * cuenta desde 1 (artboards: «#9 · Recuperación 2», «línea base:
 * lote #1»). Único sitio del repo que suma el 1.
 */
export function numeroLote(seq: number | null | undefined): string {
  return seq === null || seq === undefined ? "n/d" : `#${seq + 1}`;
}

/** Clave de comparación de las partes de un lote: sin mayúsculas ni espacios en los extremos. */
function claveLote(texto: string | null | undefined): string {
  return (texto ?? "").trim().toLowerCase();
}

/**
 * El texto recortado, o «» si está vacío o repite alguna de las partes ya
 * puestas (el nombre del dataset y la fase suelen ser el mismo texto).
 * Para cuando el nombre va en su propia línea: `sinRepetirLote(nombre, fase)`.
 */
export function sinRepetirLote(texto: string | null | undefined, ...yaPuestas: (string | null | undefined)[]): string {
  const limpio = texto?.trim() ?? "";
  return yaPuestas.some((p) => claveLote(p) === claveLote(limpio)) ? "" : limpio;
}

/**
 * Compone las partes de un lote («#5 · semana 4») en el orden dado y descarta
 * las vacías y las que repiten otra ya puesta: «#5 · semana 4» y no «#5 ·
 * semana 4 · semana 4» cuando `dataset_name` y `phase_label` coinciden.
 */
export function componerLote(...partes: (string | null | undefined)[]): string {
  const puestas: string[] = [];
  for (const parte of partes) {
    const limpia = sinRepetirLote(parte, ...puestas);
    if (limpia) puestas.push(limpia);
  }
  return puestas.join(" · ");
}

/** Alias histórico. */
export const etiquetaFase = etiquetaLote;
