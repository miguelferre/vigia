/**
 * La sonda de Vigía: figura isométrica interactiva de la portada (diapositiva
 * 1). Un modelo de IA con una sonda enchufada y un monitor con las constantes
 * (equidad, calidad, deriva); una persona usa el modelo desde un terminal y
 * sus decisiones llegan al monitor. Arranca conectada y en rango. El dibujo
 * está en `sonda-escena.ts`, el comportamiento en `sonda-logica.ts` y los
 * colores en `sonda.css`, a partir de los tokens de la aplicación.
 */

import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { escena, VIEWBOX } from "./sonda-escena";
import { montarSonda } from "./sonda-logica";
import "./sonda.css";

// Objeto estable: React 19 vuelve a escribir el innerHTML si cambia la identidad del objeto, y borraría el estado dibujado.
const ESCENA = { __html: escena() };

const ETIQUETA =
  "Figura interactiva: un modelo de IA con una sonda de Vigía enchufada. Un monitor muestra con símbolos la equidad, la calidad, la deriva y el uso. " +
  "Una persona usa el modelo desde un terminal y sus decisiones llegan al monitor. " +
  "Con la figura enfocada: clic en la sonda o Enter para desenchufarla y enchufarla; clic en la persona o la tecla c para que corrija al modelo; " +
  "d para provocar o quitar una deriva; r para reiniciar.";

export function SondaIso({ className }: { className?: string }) {
  const ref = useRef<SVGSVGElement>(null);
  const [estado, setEstado] = useState("");
  const [aviso, setAviso] = useState("");
  const [encendida, setEncendida] = useState(true);

  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    const limpiar = montarSonda(svg, { alLeer: setEstado, alEncender: setEncendida, alAnunciar: setAviso });
    return limpiar;
  }, []);

  return (
    // El fondo de la presentación avanza con un clic: aquí el clic es de la figura.
    <div className={cn("iso-sonda-holder", encendida && "glow", className)} onClick={(e) => e.stopPropagation()}>
      <svg ref={ref} className="iso-sonda on" viewBox={VIEWBOX} role="img" aria-label={ETIQUETA} tabIndex={0}>
        <defs>
          <filter id="sonda-glow" filterUnits="userSpaceOnUse" x={-2000} y={-2000} width={6000} height={6000}>
            <feGaussianBlur stdDeviation={4} result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="sonda-bloom" filterUnits="userSpaceOnUse" x={-2000} y={-2000} width={6000} height={6000}>
            <feGaussianBlur stdDeviation={9} />
          </filter>
        </defs>
        <g dangerouslySetInnerHTML={ESCENA} />
      </svg>
      <p aria-hidden="true" className="mt-1 text-center text-xs text-muted-foreground">
        {estado}
      </p>
      <p aria-live="polite" className="sr-only">
        {aviso}
      </p>
    </div>
  );
}
