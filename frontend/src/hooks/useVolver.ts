/**
 * Vuelta atrás con origen: si se llegó a la pantalla navegando dentro de la
 * app (React Router deja `idx > 0` en `window.history.state`), `volver()`
 * hace `navigate(-1)`; si se llegó por enlace directo o recarga (`idx` 0 o
 * ausente), navega a la ruta padre que pasa cada pantalla como fallback.
 *
 * Usado por `BotonVolver` en detalle de alerta, lote y monitor; este fichero no coloca el botón en ninguna
 * pantalla.
 */

import { useNavigate } from "react-router";

export interface ResultadoVolver {
  /** Ejecuta la vuelta: historial si lo hay, si no la ruta padre. */
  volver: () => void;
  /** Texto para `title`/`aria-label`: contextual cuando cae al fallback. */
  etiqueta: string;
}

function indiceHistorial(): number {
  if (typeof window === "undefined") return 0;
  const estado = window.history.state as { idx?: number } | null;
  return typeof estado?.idx === "number" ? estado.idx : 0;
}

/**
 * @param rutaPadre Ruta a la que navegar si no hay historial dentro de la app.
 * @param etiquetaPadre Nombre de esa ruta padre, para el `title` del botón
 *   («Volver a alertas»). Sin ella, el `title` es solo «Volver».
 */
export function useVolver(rutaPadre: string, etiquetaPadre?: string): ResultadoVolver {
  const navigate = useNavigate();
  const hayHistorial = indiceHistorial() > 0;

  const volver = () => {
    if (hayHistorial) {
      navigate(-1);
    } else {
      navigate(rutaPadre);
    }
  };

  const etiqueta = hayHistorial || !etiquetaPadre ? "Volver" : `Volver a ${etiquetaPadre}`;

  return { volver, etiqueta };
}
