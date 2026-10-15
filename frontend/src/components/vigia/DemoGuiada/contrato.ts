/**
 * Contrato entre la demo guiada (`DemoGuiadaProvider`, `PanelDemo`) y las
 * pantallas reales por las que pasa. Las
 * pantallas no importan el contexto de la demo: leen `?demo=` de la URL para
 * precargar el formulario y avisan por `notificarDemo` cuando el usuario
 * termina la acción. Sin demo activa, avisar no tiene efecto.
 *
 *   /modelos?demo=crear#crear-modelo
 *       abre «Crear modelo» con `PRECARGA_CREAR_DEMO`; al crearse,
 *       `notificarDemo({ tipo: "modelo-creado", projectId })`.
 *   /modelos/:id?demo=subir&guion=caso_digestivo&fase=b1#subir-datos
 *       abre la pestaña Datos y el asistente de subida con el fichero de
 *       `GET /demo/scenarios/{guion}/files/{fase}` cargado, tipo combinado,
 *       fase línea base, el mapeo de `upload_mapping` del guion precargado y
 *       «evaluar al terminar» apagado (el atado evalúa tras congelar); al
 *       terminar la ingesta, `notificarDemo({ tipo: "lote-ingerido", ... })`.
 *   /diario?demo=anotar&texto=<texto>#anotar
 *       abre la anotación humana con `texto` como motivo; al registrarla,
 *       `notificarDemo({ tipo: "anotacion-creada", projectId })`.
 */

export const PARAM_DEMO = "demo";

export type AccionDemo = "crear" | "subir" | "anotar";

const ACCIONES: readonly AccionDemo[] = ["crear", "subir", "anotar"];

/** `?demo=` de `location.search`, o `null` si no hay precarga válida. */
export function leerAccionDemo(search: string): AccionDemo | null {
  const valor = new URLSearchParams(search).get(PARAM_DEMO);
  return ACCIONES.includes(valor as AccionDemo) ? (valor as AccionDemo) : null;
}

/** Parámetros de `?demo=subir`. `null` si falta alguno. */
export function leerPrecargaSubir(search: string): { guion: string; fase: string } | null {
  const p = new URLSearchParams(search);
  const guion = p.get("guion");
  const fase = p.get("fase");
  return p.get(PARAM_DEMO) === "subir" && guion && fase ? { guion, fase } : null;
}

/** Texto de `?demo=anotar&texto=`, o `null`. */
export function leerPrecargaAnotar(search: string): string | null {
  const p = new URLSearchParams(search);
  return p.get(PARAM_DEMO) === "anotar" ? p.get("texto") : null;
}

/** Etiqueta en pantalla del tipo de modelo simulado (paso 1 del guion). */
export const ETIQUETA_MODELO_SIMULADO = "Modelo simulado de la demo";
export const MODEL_KIND_SIMULADO = "sim_logistic";

/**
 * Lo que «Crear modelo» precarga con `?demo=crear` (paso 1 de la demo guiada):
 * la etiqueta favorable es 1 = «derivar». El dominio es `reuma`, como el del guion
 * `caso_digestivo` en `sim/scenarios.py`: Digestivo es capa de nombres
 * y no un dominio técnico.
 */
export const PRECARGA_CREAR_DEMO = {
  name: "Derivación a Digestivo (demo)",
  domain: "reuma",
  model_kind: MODEL_KIND_SIMULADO,
  favorable_label: 1,
} as const;

export type EventoDemo =
  | { tipo: "modelo-creado"; projectId: number }
  | { tipo: "lote-ingerido"; projectId: number; batchId: number | null; role: string }
  | { tipo: "anotacion-creada"; projectId: number | null };

type Oyente = (evento: EventoDemo) => void;

const oyentes = new Set<Oyente>();

/** Avisa a la demo guiada de que el usuario ha terminado una acción real. */
export function notificarDemo(evento: EventoDemo): void {
  for (const oyente of oyentes) oyente(evento);
}

/** Suscribe la demo guiada; devuelve la función para darse de baja. */
export function suscribirDemo(oyente: Oyente): () => void {
  oyentes.add(oyente);
  return () => {
    oyentes.delete(oyente);
  };
}
