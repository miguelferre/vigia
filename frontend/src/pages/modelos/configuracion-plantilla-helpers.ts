/**
 * Funciones puras de la sección «Plantilla de mapeo» de Configuración:
 * pasan la plantilla del proyecto a un borrador de textos editable y
 * vuelven a ella. Sin estado ni JSX.
 */

import type { MappingTemplate } from "@/api/queries-alta";
import type { ProtectedKind } from "@/api/types";
import { claveClase, favorablesComoLista } from "@/lib/tipo-tarea";
import { FILA_VACIA, leerRangos, leerUnidad, type FilaRango } from "./alta-regresion-rango";
import { motivoFavorablesNoValidos, valorDeClase } from "./clases-multiclase";

/** Ancla de la «Zona de riesgo»: la sección de la plantilla enlaza a ella. */
export const ID_ZONA_RIESGO = "zona-de-riesgo";

export interface BorradorPlantilla {
  /** Modelo multiclase; el favorable es entonces la lista `favorables`. */
  multiclase: boolean;
  /** Clases del proyecto como claves, en su orden (solo se leen). */
  clases: string[];
  /** Conjunto favorable como claves de clase. */
  favorables: string[];
  favorable: string;
  idCol: string;
  labelCol: string;
  predictionCol: string;
  probabilityCol: string;
  timestampCol: string;
  /** Variables separadas por comas. */
  features: string;
  protectedCol: string;
  protectedKind: ProtectedKind;
  /** Grupos separados por comas; con rangos numéricos, `min..max` (por ejemplo `0..40, 41..120`). */
  unpriv: string;
  priv: string;
  /** Regresión; la unidad y el rango favorable se editan hasta congelar la línea base. */
  regresion: boolean;
  unidad: string;
  rangos: FilaRango[];
}

/** Plantilla tal como la guarda el backend (`ProjectDetail.mapping_template_json`), o `null`. */
export function leerPlantilla(json: unknown): MappingTemplate | null {
  if (!json || typeof json !== "object") return null;
  return json as MappingTemplate;
}

function gruposATexto(grupos: number[][] | string[] | undefined): string {
  if (!Array.isArray(grupos)) return "";
  return (grupos as (number[] | string)[])
    .map((g) => (Array.isArray(g) ? `${g[0]}..${g[1]}` : g))
    .join(", ");
}

/** Binario: el valor favorable como texto. Una lista (multiclase) se une con comas: nunca se recorta al primero. */
function favorableATexto(valor: MappingTemplate["favorable_label"]): string {
  if (valor === undefined || valor === null) return "";
  return Array.isArray(valor) ? valor.map(String).join(", ") : String(valor);
}

/** Unidad y rango que ya tiene el proyecto (un alta sin plantilla los guarda en el proyecto, no en la plantilla). */
export interface RegresionDelProyecto {
  unidad: string | null;
  rangos: readonly (readonly [number | null, number | null])[];
}

/**
 * `clasesProyecto`: las del proyecto, por si la plantilla aún no las trae.
 * `delProyecto`: unidad y rango del proyecto, por si la plantilla no los trae:
 * sin ellos, «Crear plantilla» y guardar sin tocar borraría el rango.
 */
export function aBorrador(
  t: MappingTemplate | null,
  multiclase = false,
  clasesProyecto: string[] = [],
  regresion = false,
  delProyecto: RegresionDelProyecto | null = null,
): BorradorPlantilla {
  const rangosFuente = (t?.favorable_ranges ?? []).length > 0 ? (t?.favorable_ranges ?? []) : (delProyecto?.rangos ?? []);
  const clasesPlantilla = (t?.classes ?? []).map(claveClase);
  return {
    multiclase,
    clases: clasesPlantilla.length > 0 ? clasesPlantilla : clasesProyecto,
    favorables: favorablesComoLista(t?.favorable_label),
    favorable: favorableATexto(t?.favorable_label),
    idCol: t?.id_col ?? "",
    labelCol: t?.label_col ?? "",
    predictionCol: t?.prediction_col ?? "",
    probabilityCol: t?.probability_col ?? "",
    timestampCol: t?.timestamp_col ?? "",
    features: (t?.feature_cols ?? []).join(", "),
    protectedCol: t?.protected_attr_col ?? "",
    protectedKind: t?.protected_kind ?? "categorical",
    unpriv: gruposATexto(t?.unpriv_groups),
    priv: gruposATexto(t?.priv_groups),
    regresion,
    unidad: t?.target_unit ?? delProyecto?.unidad ?? "",
    rangos:
      rangosFuente.length > 0
        ? rangosFuente.map(([min, max]) => ({ min: min === null ? "" : String(min), max: max === null ? "" : String(max) }))
        : [FILA_VACIA],
  };
}

const lista = (texto: string): string[] =>
  texto
    .split(/[,\n]/)
    .map((v) => v.trim())
    .filter((v) => v.length > 0);

/** Entero limpio como número (mismo criterio que el alta y `favorable_resuelto`); el resto, texto. */
function valorFavorable(texto: string): number | string | null {
  const limpio = texto.trim();
  if (limpio === "") return null;
  return /^-?\d+$/.test(limpio) ? Number(limpio) : limpio;
}

function rangos(texto: string, etiqueta: string): number[][] {
  return lista(texto).map((trozo) => {
    const partes = trozo.split("..").map((p) => Number(p.trim()));
    if (partes.length !== 2 || partes.some((n) => Number.isNaN(n))) {
      throw new Error(`${etiqueta}: escribe cada rango como «mínimo..máximo», por ejemplo 0..40.`);
    }
    return partes;
  });
}

/** Una columna vacía es «no fijada». */
const columna = (texto: string): string | null => texto.trim() || null;

/**
 * Plantilla completa lista para `PATCH /projects/{id}` (sustituye la entera).
 * La fecha, el id, la etiqueta y la predicción no son variables del modelo: se
 * sacan de la lista. `classes` y `probability_cols` (multiclase) se
 * conservan tal cual de la previa: esta pantalla aún no los edita.
 * Lanza `Error` con el motivo si el borrador no se puede guardar.
 */
export function aPlantilla(b: BorradorPlantilla, previa: MappingTemplate | null): MappingTemplate {
  const fuera = new Set(
    [b.idCol, b.labelCol, b.predictionCol, b.probabilityCol, b.timestampCol].map((c) => c.trim()),
  );
  const protegida = columna(b.protectedCol);
  const numerico = b.protectedKind === "numeric_ranges";
  const unpriv = protegida ? (numerico ? rangos(b.unpriv, "Grupo supervisado") : lista(b.unpriv)) : [];
  const priv = protegida ? (numerico ? rangos(b.priv, "Grupo de referencia") : lista(b.priv)) : [];
  if (protegida && (unpriv.length === 0 || priv.length === 0)) {
    throw new Error(
      "Atributo protegido: indica el grupo supervisado y el de referencia, o deja la columna vacía.",
    );
  }
  // En multiclase se guarda el conjunto favorable entero, con el tipo de cada clase de la previa.
  let favorableLabel: MappingTemplate["favorable_label"] = valorFavorable(b.favorable);
  if (b.multiclase) {
    const clases = previa?.classes?.length ? previa.classes : b.clases.map(valorDeClase);
    const marcadas = clases.filter((c) => b.favorables.includes(claveClase(c)));
    if (marcadas.length > 0) {
      const motivo = motivoFavorablesNoValidos(clases.map(claveClase), marcadas.map(claveClase));
      if (motivo) throw new Error(`Clases favorables: ${motivo}`);
    }
    favorableLabel = marcadas.length > 0 ? marcadas : null;
  }
  // La plantilla lleva la unidad y el rango; sin ellos, antes de congelar se perderían.
  let regresion: Pick<MappingTemplate, "target_unit" | "favorable_ranges"> = {};
  if (b.regresion) {
    const u = leerUnidad(b.unidad);
    const r = leerRangos(b.rangos);
    if (u.error ?? r.error) throw new Error(u.error ?? r.error ?? "");
    regresion = { target_unit: u.unidad, favorable_ranges: r.rangos };
  }
  return {
    ...regresion,
    favorable_label: favorableLabel,
    classes: previa?.classes?.length || !b.multiclase ? (previa?.classes ?? []) : b.clases.map(valorDeClase),
    probability_cols: previa?.probability_cols ?? [],
    prediction_col: columna(b.predictionCol),
    probability_col: columna(b.probabilityCol),
    label_col: columna(b.labelCol),
    id_col: columna(b.idCol),
    timestamp_col: columna(b.timestampCol),
    feature_cols: lista(b.features).filter((c) => !fuera.has(c)),
    protected_attr_col: protegida,
    protected_kind: b.protectedKind,
    unpriv_groups: unpriv as number[][] | string[],
    priv_groups: priv as number[][] | string[],
  };
}

/**
 * Huella de una plantilla con todas las claves y en orden fijo: dos plantillas
 * con la misma huella son la misma, así se avisa de «sin cambios» antes de que
 * el backend no deje evento. No filtra variables: una plantilla antigua con la
 * fecha entre ellas se distingue de la ya saneada.
 */
export function huellaDePlantilla(t: MappingTemplate): string {
  // Un solo favorable vale igual suelto o en lista de uno; varios se comparan sin importar el orden.
  const favorable = t.favorable_label;
  const favorables = Array.isArray(favorable)
    ? favorable.length === 1
      ? favorable.at(0)
      : [...favorable].map(String).sort()
    : favorable;
  return JSON.stringify([
    favorables ?? null,
    t.classes ?? [],
    t.probability_cols ?? [],
    t.prediction_col ?? null,
    t.probability_col ?? null,
    t.label_col ?? null,
    t.id_col ?? null,
    t.timestamp_col ?? null,
    t.feature_cols ?? [],
    t.protected_attr_col ?? null,
    t.protected_kind ?? "numeric_ranges",
    t.unpriv_groups ?? [],
    t.priv_groups ?? [],
    t.target_unit ?? null,
    t.favorable_ranges ?? [],
  ]);
}
