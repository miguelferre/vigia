/**
 * Logo de Vigía: dos círculos concéntricos, morado y blanco, y una
 * pupila morada en medio. El morado es
 * `currentColor` (el color del texto donde se pinta: `--primary` en la barra
 * lateral, el rojo de marca en la estética que lo use) y el anillo blanco es `--card` para que
 * en modo oscuro siga contrastando con el fondo. Mismo dibujo que
 * `public/favicon.svg`, que no puede leer tokens y lleva los colores fijos.
 */

import type { SVGProps } from "react";

export interface LogoVigiaProps extends SVGProps<SVGSVGElement> {
  /** Ancho y alto en píxeles (es cuadrado). */
  size?: number;
  /** Etiqueta accesible; con `decorativo` el SVG queda oculto a lectores. */
  decorativo?: boolean;
}

export function LogoVigia({ size = 24, decorativo = false, ...resto }: LogoVigiaProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      role={decorativo ? undefined : "img"}
      aria-label={decorativo ? undefined : "Vigía"}
      aria-hidden={decorativo ? "true" : undefined}
      {...resto}
    >
      <circle cx="16" cy="16" r="15" fill="currentColor" />
      <circle cx="16" cy="16" r="9" fill="var(--card)" />
      <circle cx="16" cy="16" r="4.5" fill="currentColor" />
    </svg>
  );
}

export default LogoVigia;
