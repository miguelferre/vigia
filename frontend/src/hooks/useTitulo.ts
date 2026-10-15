/**
 * Fija `document.title` a "`titulo` · Vigía" mientras la pantalla está
 * montada, y restaura el título previo al desmontar (el favicon
 * está en `frontend/public/favicon.svg`).
 *
 * Cada pantalla lo llama con su propio título.
 */

import { useEffect } from "react";

export function useTitulo(titulo: string): void {
  useEffect(() => {
    const anterior = document.title;
    document.title = `${titulo} · Vigía`;
    return () => {
      document.title = anterior;
    };
  }, [titulo]);
}
