/** Textos de los lotes con etiquetas tardías; la pantalla es `subida-tardias.tsx`. */

/** Campos que añade la ingesta de etiquetas (interfaz fijada con el backend); el tipo generado aún no los trae. */
export interface ResultadoTardias {
  lotes_con_verdad?: number[];
  lotes_reevaluados?: number[];
  lotes_a_reevaluar?: number[];
  evaluate_motivo?: string;
}

/** Nombre de un lote a partir de su id; sin lista de lotes, «#<id>». */
export type NombreDeLote = (id: number) => string;

const porId: NombreDeLote = (id) => `#${id}`;

/**
 * «#4», «#4 y #6», «#4, #6 y #8». La API devuelve ids de lote; la interfaz
 * numera con `numeroLote(seq)`, así que quien llama pasa `nombre` para no
 * mezclar las dos numeraciones (las dos son distintas).
 */
export function listaDeLotes(ids: readonly number[], nombre: NombreDeLote = porId): string {
  const t = ids.map(nombre);
  if (t.length <= 1) return t.join("");
  return `${t.slice(0, -1).join(", ")} y ${t[t.length - 1]}`;
}

/** Frase de «Se reevaluaron los lotes #4 y #6», o `null` si no hubo ninguno. */
export function fraseReevaluados(ids: readonly number[], nombre: NombreDeLote = porId): string | null {
  if (ids.length === 0) return null;
  const lista = listaDeLotes(ids, nombre);
  return ids.length === 1 ? `Se reevaluó el lote ${lista}.` : `Se reevaluaron los lotes ${lista}.`;
}

/** Aviso de los lotes que faltan por evaluar, con la numeración de la interfaz. */
export function frasePendientes(ids: readonly number[], nombre: NombreDeLote = porId): string {
  const cuantos = ids.length === 1 ? "1 lote" : `${ids.length} lotes`;
  return `Las etiquetas llegaron a ${cuantos} (${listaDeLotes(ids, nombre)}). Evalúa esos lotes para que la calidad use su verdad.`;
}
