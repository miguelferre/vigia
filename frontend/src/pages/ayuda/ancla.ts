/**
 * Desplazamiento a una entrada de la guía por su ancla (`#guia-N`). En una
 * SPA el salto nativo del navegador al hash solo ocurre en la carga inicial,
 * antes de que `useGuiaUso()` resuelva y el acordeón exista en el DOM: sin
 * esto la entrada se queda fuera de pantalla (mismo problema que resolvía
 * `programarScrollAAncla` en el onboarding, ahora retirado). Reintenta unas
 * pocas veces en vez de una sola, sin animación para no pelear con
 * `prefers-reduced-motion` ni quedarse a medias si la pestaña pierde el
 * foco justo al navegar.
 */

const MAX_INTENTOS = 10;
const INTERVALO_MS = 150;

/** Extrae el id numérico de un hash `#guia-N`, o `null` si no encaja. */
export function idDeHash(hash: string): number | null {
  const m = /^#guia-(\d+)$/.exec(hash);
  return m ? Number(m[1]) : null;
}

export function programarScrollAGuia(id: number): void {
  programarScrollAId(`guia-${id}`);
}

/** Lo mismo para cualquier id del DOM (`#datos`, la sección de la guía de datos). */
export function programarScrollAId(idDom: string): void {
  let intentos = 0;
  const intervalo = window.setInterval(() => {
    intentos += 1;
    const el = document.getElementById(idDom);
    if (el) {
      el.scrollIntoView({ behavior: "auto", block: "start" });
      window.clearInterval(intervalo);
      return;
    }
    if (intentos >= MAX_INTENTOS) window.clearInterval(intervalo);
  }, INTERVALO_MS);
}
