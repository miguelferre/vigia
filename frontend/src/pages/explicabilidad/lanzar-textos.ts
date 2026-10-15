/**
 * Textos del lanzador de explicaciones (`lanzar.tsx`): los avisos de un
 * trabajo que termina sin resultado y la ayuda del método elegido. Aparte del
 * JSX para que el componente no pase de 9 KB y los textos se lean de un sitio.
 */

export interface ResultadoExplicacion {
  id?: number;
  kind?: string;
  available?: boolean;
  motivo?: string | null;
}

/** Aviso cuando la explicación no está disponible; `null` si sí lo está. */
export function avisoNoDisponible(resultado: ResultadoExplicacion | null): string | null {
  if (!resultado || resultado.available !== false) return null;
  if (resultado.kind === "global_shap") {
    return resultado.motivo
      ? `SHAP no está disponible: ${resultado.motivo}. Prueba con la permutación.`
      : "SHAP no está disponible en este entorno. Prueba con la permutación.";
  }
  return resultado.motivo ?? "La explicación no está disponible.";
}

export const AYUDA_METODO_RESPALDO =
  "Elige entre importancia por permutación, siempre disponible, y SHAP, más preciso pero no siempre instalado.";

/**
 * «Número de registro» es la secuencia de filas del proyecto, que
 * empieza en 0 con la primera fila subida y sigue de un lote al siguiente (la
 * columna Seq de la vista del lote), no el id del fichero. El rango lo
 * sugería, pero no lo decía.
 */
export function textoRangoFila(rango: { min: number; max: number } | null): string {
  return rango
    ? `Número de fila del proyecto, desde 0 (la primera fila subida), no el id del fichero. Entre ${rango.min} y ${rango.max} para este lote.`
    : "Consultando el rango de filas del lote…";
}
