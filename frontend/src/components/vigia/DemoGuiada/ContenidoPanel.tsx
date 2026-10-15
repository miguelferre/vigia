/**
 * Lo que cuenta el panel de la demo guiada en cada paso:
 * puntos de progreso, kicker, título y frase como texto normal con un
 * fundido de 200 ms al cambiar de paso (sin morphing de letras; el
 * bloque se remonta por `key` y `motion-reduce` lo deja sin animación), «Qué
 * haces», «Qué ves», el dato real frente al esperado (`PanelDato`) o
 * «esperando al lote», la leyenda de estados bajo el dato (abierta
 * solo en el primer paso con alerta), el estado del atado de la línea base
 * (en curso y, unos segundos, hecho), y los
 * botones Anterior, Siguiente y la acción del paso.
 */

import { ArrowLeftIcon, ArrowRightIcon } from "lucide-react";

import { useGuiones } from "@/api/queries-demo";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { AccionPaso } from "./AccionPaso";
import { useDemoGuiada } from "./contexto";
import { useDatoPaso } from "./dato";
import { LeyendaEstados } from "./LeyendaEstados";
import { PanelDato } from "./PanelDato";
import { primerPasoConEstado } from "./pasos";
import { useTextoPaso } from "./texto-alertas";

/** Fundido de entrada al cambiar de paso; `tw-animate-css` ya está en `index.css`. */
const FUNDIDO = "animate-in fade-in duration-200 motion-reduce:animate-none";

export function ContenidoPanel() {
  const demo = useDemoGuiada();
  const { pasoActual: paso, pasos, hechos, resultado, projectId, atado } = demo;
  const dato = useDatoPaso(projectId, resultado, paso);
  const guionesQ = useGuiones();
  // «la lista vacía» solo si la tabla de alertas está vacía de verdad.
  const texto = useTextoPaso(projectId, paso);

  if (!paso) {
    return <p className="p-4 text-sm text-muted-foreground">Cargando el guion de la demo…</p>;
  }

  const total = pasos.length;
  const ultimo = total - 1;
  const esperandoLote = paso.fase_minima > 0 && resultado.length < paso.fase_minima;
  const faseKey = guionesQ.data?.items
    .find((s) => s.key === demo.contenido?.guion.scenario_key)
    ?.phases?.[paso.fase_minima - 1]?.key;
  const etiquetaFase = faseKey ? demo.contenido?.fases[faseKey]?.etiqueta : undefined;
  const leyendaAbierta = paso.id === primerPasoConEstado(pasos, "alerta");

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center gap-1" aria-label="Progreso de la demo">
        {pasos.map((p) => {
          const actual = p.id === paso.id;
          const hecho = hechos.has(p.id);
          return (
            <button
              key={p.id}
              type="button"
              aria-label={`Paso ${p.id + 1}: ${p.titulo}`}
              aria-current={actual ? "step" : undefined}
              onClick={() => demo.ir(p.id)}
              className={cn("h-2 rounded-full transition-[width,background-color]", actual ? "w-5" : "w-2")}
              style={{
                background: actual ? "var(--chip-active)" : hecho ? "var(--state-ok)" : "var(--line-2)",
              }}
              data-hecho={hecho ? "si" : "no"}
            />
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground tabular-nums">
        {/* numeración de 1 a 29 (`paso.id` cuenta desde 0). */}
        Paso {paso.id + 1} de {total}
        {paso.opcional ? " · opcional" : ""}
      </p>

      <div key={`texto-${paso.id}`} className={cn("flex flex-col gap-1.5", FUNDIDO)} data-paso-texto={paso.id}>
        <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{paso.kicker}</p>
        <h2 className="font-display text-lg leading-snug font-semibold tracking-tight text-balance">{paso.titulo}</h2>
        <p className="text-sm text-muted-foreground">{texto.frase}</p>
      </div>

      {paso.hace ? <Bloque titulo="Qué haces" texto={paso.hace} /> : null}
      {texto.ve ? <Bloque titulo="Qué ves" texto={texto.ve} /> : null}

      {paso.dato.metric_key !== null ? (
        esperandoLote ? (
          <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground" data-esperando="true">
            Esperando al lote{etiquetaFase ? ` «${etiquetaFase}»` : ""}: el dato aparecerá cuando se cargue.
          </p>
        ) : (
          <PanelDato paso={paso} dato={dato} />
        )
      ) : null}
      {paso.dato.estado !== null ? (
        <LeyendaEstados key={`leyenda-${paso.id}`} abierta={leyendaAbierta} projectId={projectId} />
      ) : null}

      {atado.enCurso ? (
        <p className="text-xs text-muted-foreground" role="status" data-atado="en-curso">
          Fijando la línea base y cargando las semanas 2 a 5…
        </p>
      ) : null}
      {atado.hecho ? (
        <p className="text-xs text-muted-foreground" role="status" data-atado="hecho">
          Cinco semanas de línea base evaluadas
        </p>
      ) : null}
      {atado.error ? (
        <div className="flex flex-col gap-2 rounded-md border p-3" style={{ borderColor: "var(--state-alert)" }} role="alert">
          <p className="text-xs" style={{ color: "var(--state-alert)" }}>
            No se ha podido atar la demo al modelo: {atado.error}
          </p>
          <Button type="button" size="sm" variant="outline" onClick={atado.reintentar}>
            Reintentar
          </Button>
        </div>
      ) : null}

      <div className="flex flex-col gap-2">
        <AccionPaso />
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="sm" disabled={paso.id === 0} onClick={demo.anterior}>
            <ArrowLeftIcon className="size-4" aria-hidden="true" />
            Anterior
          </Button>
          <Button type="button" size="sm" disabled={paso.id >= ultimo} onClick={demo.siguiente} className="ml-auto">
            Siguiente
            <ArrowRightIcon className="size-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function Bloque({ titulo, texto }: { titulo: string; texto: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-xs font-semibold text-tertiary">{titulo}</h3>
      <p className="text-sm">{texto}</p>
    </div>
  );
}
