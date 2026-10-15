/**
 * Contenedor de una escena a pantalla completa: kicker, título, frase opcional y
 * acción sugerida.
 *
 * Antes el texto se pintaba con `TextMorph` de torph (letra a letra).
 * Ese componente no sirve: el título cortaba palabras a mitad
 * («m / odelos», «no e / s») porque torph fija `white-space: nowrap` en su
 * raíz y, para que el texto cupiera en varias líneas, se vencía con
 * `white-space: normal`, lo que dejaba que el navegador partiera la línea
 * entre los fragmentos de torph (que no son palabras enteras); y la
 * animación por fragmentos no se veía fluida («las letras se desordenan»).
 * Se ha quitado: kicker y título son texto normal, sin trocear, con
 * `text-balance` para que las líneas queden equilibradas sin cortar
 * palabras. El cambio de escena se marca con un fundido de opacidad de
 * 200 ms: la clave del `<div>` que envuelve kicker, título y frase es el
 * propio título, así que al cambiar de diapositiva o de paso React lo
 * desmonta y remonta, y la animación de entrada (`animate-in fade-in-0`,
 * mismo idioma que el resto del repo: ver `components/ui/dialog.tsx`)
 * arranca sola. `motion-reduce:animate-none` respeta
 * `prefers-reduced-motion` sin JavaScript adicional.
 *
 * Este componente no decide la navegación (teclado, avance por clic): eso
 * es de quien lo usa (el reproductor de la presentación).
 */

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface EscenaProps {
  /** Etiqueta corta sobre el título ("Equidad", "Deriva"...). */
  kicker: string;
  titulo: string;
  /** Línea de apoyo opcional, más pequeña que el título; `null`/`undefined` la omite. */
  frase?: string | null;
  /** Botón o enlace de la acción sugerida al pie de la escena. */
  accionSugerida?: ReactNode;
  /** Contenido anclado a la pantalla real (viñetas, gráfica, tarjeta de dato...). */
  children?: ReactNode;
  /** Contenido a la derecha en pantallas anchas y debajo en estrechas (p. ej. el diagrama de una diapositiva). */
  lateral?: ReactNode;
  /**
   * Acción que se monta debajo de `lateral`, centrada en su misma columna,
   * en vez de bajo el contenido de la izquierda (la diapositiva de
   * cierre lleva el botón justo donde acaba la flecha del diagrama).
   */
  accionBajoLateral?: ReactNode;
  className?: string;
}

export function Escena({ kicker, titulo, frase, accionSugerida, children, lateral, accionBajoLateral, className }: EscenaProps) {
  const textos = (
    <div key={titulo} className="flex flex-col items-center gap-6 text-center lg:items-start lg:text-left animate-in fade-in-0 duration-200 motion-reduce:animate-none">
      <p className={cn("text-sm font-semibold tracking-wide text-muted-foreground uppercase", lateral ? "max-w-xl" : "max-w-3xl")}>
        {kicker}
      </p>
      <h1
        className={cn(
          "text-4xl font-semibold tracking-tight text-balance md:text-5xl",
          lateral ? "max-w-xl" : "max-w-3xl lg:text-6xl",
        )}
      >
        {titulo}
      </h1>
      {frase ? (
        <p className={cn("text-sm text-muted-foreground", lateral ? "max-w-xl" : "max-w-2xl")}>{frase}</p>
      ) : null}
    </div>
  );

  return (
    <section
      className={cn(
        "flex min-h-full flex-col items-center justify-center gap-6 px-6 py-16 text-center",
        "bg-background text-foreground",
        className,
      )}
    >
      {lateral ? (
        <div className="grid w-full max-w-6xl grid-cols-1 items-center gap-8 lg:grid-cols-[1fr_1fr] lg:gap-12">
          <div className="flex flex-col items-center gap-6 text-center lg:items-start lg:text-left">
            {textos}
            {children ? <div className="w-full">{children}</div> : null}
            {accionSugerida ? <div className="mt-2 flex items-center gap-3">{accionSugerida}</div> : null}
          </div>
          <div className="flex min-h-[380px] w-full flex-col items-center justify-center gap-4">
            {lateral}
            {accionBajoLateral ? <div className="flex items-center gap-3">{accionBajoLateral}</div> : null}
          </div>
        </div>
      ) : (
        <>
          {textos}
          {children}
          {accionSugerida ? <div className="mt-2 flex items-center gap-3">{accionSugerida}</div> : null}
        </>
      )}
    </section>
  );
}
