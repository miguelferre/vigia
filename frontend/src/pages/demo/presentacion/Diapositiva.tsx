/**
 * Una diapositiva de la presentación: a pantalla completa, el texto a la izquierda (kicker, título,
 * `puntos` como viñetas con marcador `--chart-1`, la `frase` cuando el guion
 * la trae, el chip de estado y las notas del ponente, visibles solo con
 * `notasVisibles`, tecla `N`) y su figura a la derecha, del 55 al 60 % del
 * ancho (`2fr_3fr`). La figura propia viene de `DIAGRAMAS[id]`; la última
 * lleva dentro el enlace «Ejecutar la demo» (`D10`). Las fuentes van al pie de
 * la diapositiva, en letra pequeña y sin fecha de consulta. Ya no usa
 * `Escena`: esa rejilla es de la demo guiada y reparte el ancho a partes
 * iguales.
 */

import type { Diapositiva as DiapositivaContenido } from "@/api/queries-contenido";
import { DIAGRAMAS } from "@/components/vigia/diagramas";

function Fuentes({ fuente }: { fuente: DiapositivaContenido["fuente"] }) {
  if (fuente.length === 0) return null;
  return (
    <ul className="mx-auto mt-6 w-full max-w-[1500px] space-y-0.5 text-left text-[11px] leading-snug text-muted-foreground">
      {fuente.map((f) => (
        <li key={f.texto}>
          {f.url ? (
            <a href={f.url} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-foreground">
              {f.texto}
            </a>
          ) : (
            f.texto
          )}
        </li>
      ))}
    </ul>
  );
}

/** Lista de viñetas a cuerpo grande, marcador `--chart-1` en vez del punto por defecto. */
function ListaPuntos({ puntos }: { puntos: string[] }) {
  return (
    <ul className="flex w-full flex-col gap-3 text-left text-lg font-medium text-balance lg:text-xl xl:text-2xl">
      {puntos.map((punto) => (
        <li key={punto} className="flex items-start gap-3">
          <span aria-hidden="true" className="mt-[0.6em] size-2 shrink-0 rounded-full" style={{ background: "var(--chart-1)" }} />
          <span>{punto}</span>
        </li>
      ))}
    </ul>
  );
}

export interface DiapositivaProps {
  diapositiva: DiapositivaContenido;
  notasVisibles: boolean;
}

export function Diapositiva({ diapositiva, notasVisibles }: DiapositivaProps) {
  const Diagrama = DIAGRAMAS[diapositiva.id];

  return (
    <section className="flex flex-1 flex-col justify-center bg-background py-4 text-foreground">
      <div className="mx-auto grid w-full max-w-[1500px] grid-cols-1 items-center gap-8 lg:grid-cols-[2fr_3fr]">
        <div
          key={diapositiva.titulo}
          className="flex flex-col items-start gap-5 text-left animate-in fade-in-0 duration-200 motion-reduce:animate-none"
        >
          <p className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">{diapositiva.kicker}</p>
          <h1 className="text-3xl font-semibold tracking-tight text-balance lg:text-4xl xl:text-5xl">{diapositiva.titulo}</h1>
          <ListaPuntos puntos={diapositiva.puntos} />
          {diapositiva.frase ? <p className="max-w-xl text-sm text-muted-foreground">{diapositiva.frase}</p> : null}
          {diapositiva.estado ? (
            <span
              className="inline-flex max-w-md items-center rounded-full px-2.5 py-1 text-xs font-medium"
              style={{ background: "var(--state-warn-fill)", color: "var(--state-on-fill)" }}
            >
              {diapositiva.estado}
            </span>
          ) : null}
          {notasVisibles ? (
            <p className="max-w-2xl rounded-lg border border-dashed border-[var(--line-2)] bg-card p-3 text-xs text-muted-foreground">
              <span className="font-semibold text-foreground">Notas del ponente. </span>
              {diapositiva.notas}
            </p>
          ) : null}
        </div>
        <div className="flex w-full items-center justify-center">
          {Diagrama ? <Diagrama className="text-foreground" /> : null}
        </div>
      </div>
      <Fuentes fuente={diapositiva.fuente} />
    </section>
  );
}

export default Diapositiva;
