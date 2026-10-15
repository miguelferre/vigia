/**
 * Ancho de un contenedor por `ResizeObserver`:
 * devuelve un `ref` de función y el ancho entero en píxeles del nodo al que
 * se asocie, 0 antes de la primera medición. Es un `ref` de función, y no un
 * `useRef`, porque el nodo puede aparecer después del montaje (el violín
 * enseña un `Skeleton` mientras cargan los detalles): el observador se
 * engancha cuando el nodo existe, no solo en el primer efecto. Pensado para
 * SVG propios que necesitan saber cuánto hueco tienen.
 */

import { useEffect, useState } from "react";

export function useAnchoContenedor<T extends HTMLElement>(): [(nodo: T | null) => void, number] {
  const [nodo, setNodo] = useState<T | null>(null);
  const [ancho, setAncho] = useState(0);

  useEffect(() => {
    if (!nodo) return;
    const observador = new ResizeObserver((entradas) => {
      const entrada = entradas[0];
      if (entrada) setAncho(Math.floor(entrada.contentRect.width));
    });
    observador.observe(nodo);
    return () => observador.disconnect();
  }, [nodo]);

  return [setNodo, ancho];
}

export default useAnchoContenedor;
