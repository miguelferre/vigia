/**
 * Estado de `alertas/index.tsx` que vive en la URL: `?panel=<id>` (enlace
 * directo al detalle) y `?resaltar=<id>` (fila que
 * llega marcada desde fuera: onboarding, CX-1 y el paso de la demo guiada
 * que enseña una alerta). Aparte para que `index.tsx` quede
 * por debajo de 9 KB.
 */

import { useEffect, useRef, useState } from "react";

import type { Alert } from "@/api/types";

export function usePanelAlerta(params: URLSearchParams, setParams: (params: URLSearchParams) => void) {
  const panelAlertId = Number(params.get("panel")) || null;

  const abrirPanel = (id: number) => {
    const next = new URLSearchParams(params);
    next.set("panel", String(id));
    setParams(next);
  };
  const cerrarPanel = () => {
    const next = new URLSearchParams(params);
    next.delete("panel");
    setParams(next);
  };

  return { panelAlertId, abrirPanel, cerrarPanel };
}

/**
 * El resaltado de `?resaltar=` no se apaga quitando el parámetro de la URL
 * (repetir el enlace debe volver a resaltar), sino solo pasados unos
 * segundos; el desvanecido de 1,5 s lo pinta `DataTableFila` con
 * `transition-colors` en cuanto `resaltadoApagado` pasa a verdadero.
 */
export function useResaltadoAlerta(params: URLSearchParams, filas: Alert[]) {
  const idResaltado = Number(params.get("resaltar")) || null;

  // Al cambiar el id resaltado, el resaltado vuelve a encenderse en el
  // render (patrón del repo: ajuste de estado con una clave, no `setState`
  // dentro del efecto); el efecto solo programa el apagado.
  const [resaltadoApagado, setResaltadoApagado] = useState(false);
  const [idResaltadoVisto, setIdResaltadoVisto] = useState<number | null>(idResaltado);
  if (idResaltado !== idResaltadoVisto) {
    setIdResaltadoVisto(idResaltado);
    setResaltadoApagado(false);
  }
  useEffect(() => {
    if (idResaltado === null) return undefined;
    const id = window.setTimeout(() => setResaltadoApagado(true), 4000);
    return () => window.clearTimeout(id);
  }, [idResaltado]);

  // Desplaza la fila resaltada a la vista una vez, en cuanto exista en el DOM
  // (la lista llega por REST): `data-recien` ya lo pinta `DataTableFila` a
  // partir de `filaResaltada`. El `ref` evita repetir el scroll en cada
  // refetch mientras `idResaltado` no cambie.
  const idResaltadoDesplazado = useRef<number | null>(null);
  useEffect(() => {
    if (idResaltado === null || idResaltadoDesplazado.current === idResaltado) return;
    const fila = document.getElementById("cx1")?.querySelector('[data-recien="true"]');
    if (!fila) return;
    idResaltadoDesplazado.current = idResaltado;
    fila.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [idResaltado, filas]);

  return { idResaltado, resaltadoApagado };
}
