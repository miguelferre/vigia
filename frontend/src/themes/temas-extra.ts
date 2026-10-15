/**
 * Estéticas adicionales al tema personal. Esta versión es la pública: no hay
 * ninguna. El build completo sustituye este módulo por `temas-privados.ts`
 * (alias de `vite.config.ts`, solo si el fichero existe y `VITE_TEMA` no vale
 * `miguel`), que registra sus tokens CSS y su entrada aquí.
 */

export interface TemaExtra {
  valor: string;
  /** Texto del menú de estética. */
  etiqueta: string;
  /** Texto corto de Ajustes. */
  etiquetaCorta: string;
}

export const TEMAS_EXTRA: TemaExtra[] = [];
