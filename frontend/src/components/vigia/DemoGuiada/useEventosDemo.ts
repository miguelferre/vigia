/**
 * La demo guiada escuchando a las pantallas reales (contrato de
 * `contrato.ts`): `modelo-creado` fija el proyecto y da por hecho el
 * paso 1; `lote-ingerido` con la línea base ATA la reproducción al proyecto
 * con `POST /demo/runs {project_id}` (el backend adopta ese lote como fase 0:
 * lo etiqueta, congela la línea base, explica y evalúa, y
 * reproduce además las cuatro semanas siguientes de línea base) y da
 * por hecho el 2; `anotacion-creada` da por hecho el paso de la anotación.
 * Los ids de los tres pasos vienen del guion (`pasosConEvento`), no de
 * constantes. El atado que falla se queda en el panel con su mensaje y un
 * reintento, no en un toast que desaparece.
 *
 * el atado ya no exige `runId ===
 * null`; ata también si la reproducción cargada (`run`) es de otro proyecto
 * que el del lote, o si `runId` apunta a una que ya no existe (`runEs404`).
 * `hecho` cuenta unos segundos tras un atado bueno para que el panel lo
 * enseñe como paso propio antes de darlo por pasado.
 *
 * El oyente se registra una vez y lee el estado más reciente por `ref`:
 * `suscribirDemo` no debe darse de alta y de baja en cada render.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, mensajeDeError } from "@/api/client";
import { useCrearReproduccion } from "@/api/queries-demo";
import { qk } from "@/api/queries";
import type { DemoRun, ProjectDetail } from "@/api/types";

import { MODEL_KIND_SIMULADO, suscribirDemo, type EventoDemo } from "./contrato";
import type { AtadoDemo } from "./contexto";

/** «Cinco semanas de línea base evaluadas» antes de dar el paso por hecho. */
const HECHO_MS = 6000;

export interface ArgumentosEventos {
  runId: number | null;
  /** Reproducción de `runId` (`Provider`, `useReproduccion`), o `null` si no hay o aún no ha llegado. */
  run: DemoRun | null;
  /** `runId` no es `null` pero la consulta de `run` devolvió 404: ya no existe. */
  runEs404: boolean;
  /** Ids de los pasos que esperan a `modelo-creado`, `lote-ingerido` y `anotacion-creada`. */
  pasos: { crear: number | null; subir: number | null; anotar: number | null };
  scenarioKey: string | undefined;
  withHuman: boolean;
  alCrearModelo: (projectId: number) => void;
  alAtar: (runId: number, projectId: number) => void;
  marcarHecho: (n: number) => void;
}

export function useEventosDemo(args: ArgumentosEventos): AtadoDemo {
  const crear = useCrearReproduccion();
  const queryClient = useQueryClient();
  // `mutate` es estable entre renders (TanStack Query 5); el objeto `crear` no.
  const { mutate } = crear;
  const [pendiente, setPendiente] = useState<number | null>(null);
  const [hecho, setHecho] = useState(false);
  const ultimo = useRef(args);
  useEffect(() => {
    ultimo.current = args;
  });

  useEffect(() => {
    if (!hecho) return;
    const t = setTimeout(() => setHecho(false), HECHO_MS);
    return () => clearTimeout(t);
  }, [hecho]);

  const atar = useCallback(
    (projectId: number) => {
      const { scenarioKey, withHuman, alAtar, marcarHecho, pasos } = ultimo.current;
      if (!scenarioKey) return;
      setPendiente(projectId);
      setHecho(false);
      mutate(
        { scenario_key: scenarioKey, project_id: projectId, with_human: withHuman, source: "canned" },
        {
          onSuccess: (run) => {
            if (run.id !== null) alAtar(run.id, run.project_id);
            if (pasos.subir !== null) marcarHecho(pasos.subir);
            setHecho(true);
          },
        },
      );
    },
    [mutate],
  );

  /**
   * La reproducción solo se ata a un proyecto del simulador: el backend
   * responde 422 a cualquier otro y la demo no debe disparar nada sobre un
   * proyecto real. Si no se puede comprobar, no se ata.
   */
  const esDelSimulador = useCallback(
    async (projectId: number): Promise<boolean> => {
      try {
        const p = await queryClient.fetchQuery({
          queryKey: qk.project(projectId),
          queryFn: () => api.get<ProjectDetail>(`/projects/${projectId}`),
          staleTime: 0,
        });
        const activa = p.versions.find((v) => v.id === p.active_version_id);
        return activa?.model_kind === MODEL_KIND_SIMULADO;
      } catch {
        return false;
      }
    },
    [queryClient],
  );

  useEffect(() => {
    return suscribirDemo((evento: EventoDemo) => {
      const { runId, run, runEs404, alCrearModelo, marcarHecho, pasos } = ultimo.current;
      if (evento.tipo === "modelo-creado") {
        alCrearModelo(evento.projectId);
        if (pasos.crear !== null) marcarHecho(pasos.crear);
      } else if (evento.tipo === "lote-ingerido") {
        const otroProyecto = run !== null ? run.project_id !== evento.projectId : runEs404;
        if (evento.role === "baseline" && (runId === null || otroProyecto)) {
          const projectId = evento.projectId;
          void esDelSimulador(projectId).then((simulado) => {
            if (simulado) atar(projectId);
          });
        }
      } else if (evento.tipo === "anotacion-creada") {
        if (pasos.anotar !== null) marcarHecho(pasos.anotar);
      }
    });
  }, [atar, esDelSimulador]);

  return {
    enCurso: crear.isPending,
    error: crear.isError ? mensajeDeError(crear.error) : null,
    hecho,
    reintentar: () => {
      if (pendiente !== null) atar(pendiente);
    },
  };
}
