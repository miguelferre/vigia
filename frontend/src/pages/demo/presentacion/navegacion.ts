/**
 * Estado de la presentación en la URL (`?diapositiva=N`, 1 a `total`): navegación por clic en el fondo, flechas y espacio (adelante),
 * flecha izquierda (atrás), Escape (sale a `/`, también a pantalla completa:
 * la presentación siempre se ve en modo presentación) y `N` (notas del
 * ponente). Mismo patrón de partido en la URL que
 * `useEstadoPanel.ts` (`replace`, sin apilar historial por cada paso).
 *
 * `Escena` ya no usa torph: no hay animación
 * por fragmento que pueda «acumularse» entre dos transiciones rápidas,
 * así que la medición de tiempo
 * entre cambios (`transicionRapida`, `DURACION_MS`) desaparece con él. El
 * fundido de 200 ms de `Escena` se rearma solo, por clave de React, cada vez
 * que cambia el título.
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

const PARAM = "diapositiva";

export interface NavegacionPresentacion {
  /** Índice 1-basado de la diapositiva actual. */
  indice: number;
  ir: (siguiente: number) => void;
  notasVisibles: boolean;
}

export function useNavegacionPresentacion(total: number): NavegacionPresentacion {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [notasActivadas, setNotasActivadas] = useState(false);
  const notasVisibles = notasActivadas;

  const crudo = Number(params.get(PARAM));
  const indice = Number.isInteger(crudo) && crudo >= 1 && crudo <= total ? crudo : 1;

  const ir = useCallback(
    (siguiente: number) => {
      const acotado = Math.max(1, Math.min(total, siguiente));
      if (acotado === indice) return;
      const next = new URLSearchParams(params);
      next.set(PARAM, String(acotado));
      setParams(next, { replace: true });
    },
    [indice, params, setParams, total],
  );

  useEffect(() => {
    function alTeclado(e: KeyboardEvent) {
      const objetivo = e.target as HTMLElement | null;
      if (objetivo && /^(input|textarea|select)$/i.test(objetivo.tagName)) return;
      if (e.key === "ArrowRight" || e.key === " " || e.code === "Space") {
        e.preventDefault();
        ir(indice + 1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        ir(indice - 1);
      } else if (e.key === "Escape") {
        navigate("/");
      } else if (e.key === "n" || e.key === "N") {
        setNotasActivadas((v) => !v);
      }
    }
    window.addEventListener("keydown", alTeclado);
    return () => window.removeEventListener("keydown", alTeclado);
  }, [indice, navigate, ir]);

  return { indice, ir, notasVisibles };
}
