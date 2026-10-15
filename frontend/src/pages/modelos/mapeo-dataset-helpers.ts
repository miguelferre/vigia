/**
 * Funciones puras de `mapeo-dataset.tsx`, partidas para quedar por debajo
 * de 9 KB: nada de estado ni JSX aquí.
 */

import type { ColumnMappingOut, Dataset, ProtectedKind } from "@/api/types";

/** Campos que puede fijar la plantilla del proyecto: si el usuario los
 * cambia respecto de lo que llegó sugerido, el mapeo se aparta de ella. */
export function huellaPlantilla(m: {
  favorableLabel: string;
  idCol: string;
  protectedCol: string;
  protectedKind: ProtectedKind;
  features: string[];
}): string {
  return JSON.stringify([m.favorableLabel, m.idCol, m.protectedCol, m.protectedKind, [...m.features].sort()]);
}

function tieneNombre(v: unknown): v is { name: string } {
  return !!v && typeof v === "object" && typeof (v as { name?: unknown }).name === "string";
}

export function nombresColumnas(dataset: Dataset): string[] {
  // `columns` es `DatasetColumn[] | string[] | null`: la ingesta de datos guarda
  // columnas descritas y la del diario de uso solo los nombres. Se recorre como
  // lista de valores sueltos y se quedan las que traen `name`, igual que antes.
  const columnas: unknown[] = Array.isArray(dataset.columns) ? dataset.columns : [];
  return columnas.filter(tieneNombre).map((c) => c.name);
}

export function primerRango(valores: number[][] | string[] | undefined): [string, string] {
  const rango = Array.isArray(valores) && Array.isArray(valores[0]) ? (valores[0] as number[]) : null;
  return rango ? [String(rango[0] ?? ""), String(rango[1] ?? "")] : ["", ""];
}

/** Lista de grupos categóricos ya sugeridos, como texto separado por comas. */
export function categoricosATexto(valores: number[][] | string[] | undefined): string {
  if (!Array.isArray(valores) || valores.length === 0) return "";
  if (typeof valores[0] !== "string") return "";
  return (valores as string[]).join(", ");
}

export function textoACategoricos(texto: string): string[] {
  return texto
    .split(",")
    .map((v) => v.trim())
    .filter((v) => v.length > 0);
}

/** Rango numérico de un grupo (`[[mín, máx]]`), o ninguno si falta un extremo. */
export function rangoNumerico(min: string, max: string): number[][] {
  return min !== "" && max !== "" ? [[Number(min), Number(max)]] : [];
}

/** Valor favorable de la plantilla o del mapeo: vacío es `null`, un entero limpio es número y el resto, texto. */
export function valorFavorable(texto: string): number | string | null {
  const limpio = texto.trim();
  if (limpio === "") return null;
  return /^-?\d+$/.test(limpio) ? Number(limpio) : limpio;
}

/** Id estable a partir de la etiqueta: sin acentos ni espacios, para `htmlFor`/`id`. */
export function idDeEtiqueta(etiqueta: string): string {
  return `mc-${etiqueta
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "")}`;
}

/**
 * Sugerencia de mapeo para un fichero de etiquetas tardías:
 * solo conserva lo que ese fichero puede traer (id, etiqueta y fecha). Quita
 * las variables, el atributo protegido y el favorable de la plantilla, que
 * el fichero no tiene y el servidor rechazaba como «columnas que no están».
 */
export function soloIdYEtiqueta(
  m: ColumnMappingOut | null | undefined,
  activo: boolean,
): ColumnMappingOut | null | undefined {
  if (!m || !activo) return m;
  return { ...m, feature_cols: [], protected_attr_col: null, unpriv_groups: [], priv_groups: [], favorable_label: null };
}
