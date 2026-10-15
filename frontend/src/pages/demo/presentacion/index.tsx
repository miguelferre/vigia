/**
 * Presentación (10
 * diapositivas de `GET /content/presentacion`). Contrato
 * con `pages/demo/index.tsx`: componente sin props que lee y
 * escribe `?diapositiva=N` por sí mismo y, en la última diapositiva, lleva a
 * `/demo?paso=0`.
 *
 * Pantalla completa: al montarse activa el modo
 * presentación (sin barra lateral ni cabecera) y al desmontarse lo deja como
 * estaba, no como lo pidió esta página. Por eso «Ejecutar la demo» arranca la
 * demo guiada con la barra lateral, igual que si se entrara en ella sin pasar
 * por la presentación.
 *
 * Avance por clic en el fondo (los controles internos paran la propagación
 * para no disparar un avance doble, igual que hacía `Recorrido.tsx` del
 * onboarding), flechas y espacio; retroceso con flecha izquierda; Escape
 * sale a `/`. Puntos de progreso clicables y
 * contador «n / 10».
 */

import { useEffect, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import { useNavigate } from "react-router";
import { ArrowLeftIcon, ArrowRightIcon, XIcon } from "lucide-react";

import { usePresentacion } from "@/api/queries-contenido";
import { EmptyState, useModoPresentacion } from "@/components/vigia";
import { Button } from "@/components/ui/button";

import { Diapositiva } from "./Diapositiva";
import { useNavegacionPresentacion } from "./navegacion";

export function Presentacion() {
  const navigate = useNavigate();
  const { activo, activar, desactivar } = useModoPresentacion();
  // Estado con el que se entró: se restituye al salir.
  const [modoPrevio] = useState(activo);
  useEffect(() => {
    activar();
    return () => {
      if (!modoPrevio) desactivar();
    };
  }, [activar, desactivar, modoPrevio]);
  const contenido = usePresentacion();
  const diapositivas = contenido.data?.diapositivas ?? [];
  const total = diapositivas.length;

  const { indice, ir, notasVisibles } = useNavegacionPresentacion(Math.max(total, 1));

  if (contenido.isLoading) {
    return <p className="p-8 text-sm text-muted-foreground">Cargando la presentación…</p>;
  }
  if (contenido.isError || total === 0) {
    return (
      <EmptyState
        className="m-8"
        titulo="No se ha podido cargar la presentación"
        descripcion="Reintenta o entra directamente en la demo."
        accion={
          <Button variant="outline" size="sm" onClick={() => navigate("/demo?paso=0")}>
            Ir a la demo
          </Button>
        }
      />
    );
  }

  const diapositiva = diapositivas[indice - 1] ?? diapositivas[0]!;

  const alClicFondo = (e: ReactMouseEvent<HTMLDivElement>) => {
    const interactivo = (e.target as HTMLElement).closest("button, a, [role='button']");
    if (interactivo) return;
    ir(indice + 1);
  };

  return (
    <div className="flex min-h-[calc(100vh-3rem)] flex-col" onClick={alClicFondo}>
      <div className="flex items-center justify-between gap-2 px-4 py-2">
        <div className="flex flex-wrap items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
          {diapositivas.map((d, i) => (
            <button
              key={d.id}
              type="button"
              aria-label={`Ir a la diapositiva ${i + 1}: ${d.titulo}`}
              aria-current={i + 1 === indice}
              onClick={() => ir(i + 1)}
              className={
                i + 1 === indice
                  ? "h-2 w-6 rounded-full bg-chip-active"
                  : "h-2 w-2 rounded-full bg-muted-foreground/40 hover:bg-muted-foreground"
              }
            />
          ))}
        </div>
        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1.5 hover:bg-muted"
            aria-label="Salir de la presentación"
            title="Salir (Esc)"
            onClick={() => navigate("/")}
          >
            <XIcon className="size-4" aria-hidden="true" />
            Salir
          </Button>
        </div>
      </div>

      <Diapositiva diapositiva={diapositiva} notasVisibles={notasVisibles} />

      <div className="flex items-center justify-center gap-3 pb-8" onClick={(e) => e.stopPropagation()}>
        <Button type="button" variant="outline" size="icon" disabled={indice === 1} onClick={() => ir(indice - 1)}>
          <ArrowLeftIcon className="size-4" aria-hidden="true" />
        </Button>
        <span className="text-sm text-muted-foreground tabular-nums">
          {indice} / {total}
        </span>
        <Button type="button" variant="outline" size="icon" disabled={indice === total} onClick={() => ir(indice + 1)}>
          <ArrowRightIcon className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

export default Presentacion;
