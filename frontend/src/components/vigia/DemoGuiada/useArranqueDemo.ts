/**
 * Arranque y reinicio de la demo guiada, separados de `Provider.tsx` para no
 * pasar de 9 KB.
 *
 * `empezar(0)` sin `runId` (no hay `?run=` en la URL) arranca de cero: el
 * estado de una demo anterior (de otro proyecto, o con una reproducción ya
 * inexistente) no se arrastra. Con `runId` (adopción por `?run=`, capturas)
 * se conserva el comportamiento previo: solo se rellena lo que falta, y
 * «Continuar» desde un paso > 0 no pierde nada.
 *
 * ese arranque de cero es, hoy, el único sitio silencioso (sin
 * copia que prometa nada sobre el proyecto anterior: `BotonReiniciarDemo.tsx`
 * ya avisa de que «el modelo creado se conserva» cuando reinicia sin
 * reproducción, así que ese otro camino no se toca aquí). Antes de arrancar,
 * si la sesión venía de un proyecto de demo (`is_demo`) que se quedó sin
 * ningún lote (`counts.batches === 0`, nunca se llegó a ingerir nada), se
 * borra (`DELETE /projects/{id}?confirm=true`; `nuevo-modelo-dialog.tsx`
 * ya evita el choque de nombres con «(demo) 2», pero el proyecto vacío
 * seguía listado en /modelos). Mejor esfuerzo: cualquier fallo (proyecto ya
 * borrado, con datos, sin red) no bloquea el arranque.
 *
 * `reiniciar()` borra el estado también cuando `POST /demo/runs/{id}/reset`
 * devuelve 404 (la reproducción ya no existe: nada que reiniciar); con
 * cualquier otro error deja el estado intacto y relanza la excepción para
 * que `MotivoDialog` la enseñe y permita reintentar.
 */

import { useCallback } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { NavigateFunction } from "react-router";

import { api, ApiError } from "@/api/client";
import { useReiniciar } from "@/api/queries-demo";
import type { ActorBody, ProjectDetail } from "@/api/types";

import type { ContextoDestino } from "./destino";
import { borrarEstadoDemo, ESTADO_INICIAL, type EstadoDemo } from "./progreso";

/**
 * borra `projectId` si es un proyecto de demo sin ningún lote
 * ingerido. Mejor esfuerzo, en silencio: nunca bloquea ni interrumpe el
 * arranque de una demo nueva, y nunca toca un proyecto con datos.
 */
async function borrarSiDemoVacio(projectId: number | null): Promise<void> {
  if (projectId === null) return;
  try {
    const proyecto = await api.get<ProjectDetail>(`/projects/${projectId}`);
    if (proyecto.is_demo && proyecto.counts.batches === 0) {
      await api.del(`/projects/${projectId}`, undefined, { params: { confirm: true } });
    }
  } catch {
    // Proyecto ya borrado, con datos, o sin red: no es motivo para no arrancar.
  }
}

export interface ArgumentosArranque {
  ir: (n: number, ctx?: ContextoDestino) => void;
  ctxDestino: ContextoDestino;
  /** `estado.runId` vigente, para saber si `reiniciar` tiene reproducción que borrar. */
  runIdActual: number | null;
  proyectoSesion: number | null;
  setProjectId: (id: number | null) => void;
  setEstado: Dispatch<SetStateAction<EstadoDemo>>;
  navigate: NavigateFunction;
}

export interface ResultadoArranque {
  /** Activa la demo en `paso` (0 por defecto), adoptando una reproducción si se pasa. */
  empezar: (paso?: number, runId?: number | null, projectId?: number | null) => void;
  /** `POST /demo/runs/{id}/reset` si hay reproducción, borra el estado y vuelve a `/demo`. */
  reiniciar: (cuerpo: ActorBody) => Promise<void>;
}

export function useArranqueDemo(args: ArgumentosArranque): ResultadoArranque {
  const { ir, ctxDestino, runIdActual, proyectoSesion, setProjectId, setEstado, navigate } = args;

  const empezar = useCallback(
    (paso = 0, runId: number | null = null, projectId: number | null = null) => {
      if (paso === 0 && runId === null) {
        // mejor esfuerzo, no se espera antes de arrancar de cero.
        void borrarSiDemoVacio(proyectoSesion);
        setEstado(() => ({ ...ESTADO_INICIAL, activa: true }));
        ir(0, { ...ctxDestino, projectId: null });
        return;
      }
      setEstado((s) => ({
        ...s,
        activa: true,
        plegado: false,
        runId: runId ?? s.runId,
        projectId: projectId ?? s.projectId,
      }));
      if (projectId !== null && proyectoSesion !== projectId) setProjectId(projectId);
      ir(paso, projectId !== null ? { ...ctxDestino, projectId } : ctxDestino);
    },
    [ir, ctxDestino, proyectoSesion, setProjectId, setEstado],
  );

  const { mutateAsync: reiniciarRun } = useReiniciar();
  const reiniciar = useCallback(
    async (cuerpo: ActorBody) => {
      if (runIdActual !== null) {
        try {
          await reiniciarRun({ runId: runIdActual, body: { ...cuerpo, confirm: true } });
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 404)) throw error;
        }
      }
      borrarEstadoDemo();
      setEstado(() => ({ ...ESTADO_INICIAL }));
      navigate("/demo");
    },
    [runIdActual, reiniciarRun, setEstado, navigate],
  );

  return { empezar, reiniciar };
}
