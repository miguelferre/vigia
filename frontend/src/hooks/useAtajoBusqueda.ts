/**
 * Atajo global `Ctrl K` (`Cmd K` en Mac) del buscador de la barra lateral
 * navega a `/ayuda?q=<texto>` con el texto que
 * haya en el campo de búsqueda en ese momento.
 *
 * `/ayuda` no lee todavía el parámetro `q` de la URL (su filtro es estado
 * interno, `pages/ayuda/index.tsx`).
 */

import { useEffect } from "react";
import { useNavigate } from "react-router";

export function useAtajoBusqueda(texto: string): void {
  const navigate = useNavigate();

  useEffect(() => {
    function alPulsar(e: KeyboardEvent) {
      const esAtajo = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k";
      if (!esAtajo) return;
      e.preventDefault();
      const q = texto.trim();
      navigate(q ? `/ayuda?q=${encodeURIComponent(q)}` : "/ayuda");
    }
    window.addEventListener("keydown", alPulsar);
    return () => window.removeEventListener("keydown", alPulsar);
  }, [texto, navigate]);
}
