/**
 * Diapositiva 1 (portada): la sonda de Vigía, una figura isométrica
 * interactiva. Sustituye al ciclo de tres pasos
 * con el logo en medio: ahora el mecanismo se ve en un
 * objeto. Un modelo de IA con una sonda enchufada, una persona que usa el
 * modelo y un monitor con equidad, calidad y deriva. El dibujo, el
 * comportamiento y los colores viven en `./iso/`.
 */

import { SondaIso } from "./iso/SondaIso";

export function D01({ className }: { className?: string }) {
  return <SondaIso className={className} />;
}

export default D01;
