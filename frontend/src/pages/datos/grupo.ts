/**
 * Traducción best-effort de `group_code` numérico a partir del mapeo del
 * dataset del lote. El servidor ya envía las etiquetas:
 * `CompositionRow.group_label` y `Record.group_label` ya llegan del servidor
 * (`composicion.tsx` y `registros.tsx` los leen primero). Esta función queda
 * solo como RESPALDO para cuando el campo del servidor es `null` (sin mapeo
 * asociado al lote) y para cualquier otro consumidor que no lo tenga a mano.
 * Convención observada del motor: 0 = grupo no privilegiado (`unpriv_groups`),
 * 1 = grupo privilegiado (`priv_groups`); cualquier otro código (p. ej. -1)
 * cae fuera de ambos rangos. A diferencia del campo del servidor, aquí solo
 * se usa el primer rango de cada grupo y el separador es guion largo.
 */

import type { ColumnMappingOut } from "@/api/types";

function formatoRango(valores: number[][] | string[] | undefined): string | null {
  if (!Array.isArray(valores) || valores.length === 0) return null;
  const primero = valores[0];
  if (Array.isArray(primero)) return `${primero[0]}–${primero[1]}`;
  return valores.join(", ");
}

/** Etiqueta legible de un `group_code`, o `null` si no se puede derivar. */
export function etiquetaGrupo(
  groupCode: number,
  mapping: ColumnMappingOut | null | undefined,
): string | null {
  if (!mapping || mapping.protected_kind !== "numeric_ranges") return null;
  if (groupCode === 0) return formatoRango(mapping.unpriv_groups);
  if (groupCode === 1) return formatoRango(mapping.priv_groups);
  return "otros";
}

/**
 * Papel del grupo, convención del motor: 0 = supervisado, 1 =
 * referencia; cualquier otro código (p. ej. -1) no tiene papel (`null`).
 */
export function papelDeGrupo(groupCode: number): "supervisado" | "referencia" | null {
  if (groupCode === 0) return "supervisado";
  if (groupCode === 1) return "referencia";
  return null;
}

/**
 * Etiqueta legible con papel: rango con su papel
 * («18-35 · supervisado»), o solo el rango/«otros» si el grupo no tiene
 * papel. Compartida entre la tabla de composición y la de registros para
 * que un mismo grupo se lea igual en ambas.
 */
export function etiquetaGrupoConPapel(groupCode: number, rango: string | null): string {
  const papel = papelDeGrupo(groupCode);
  const texto = rango ?? String(groupCode);
  return papel ? `${texto} · ${papel}` : texto;
}
