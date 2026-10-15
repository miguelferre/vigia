/**
 * Proveedor de la demo guiada: el estado en
 * `localStorage` `vigia-demo`, el guion de `GET /content/demo`, la
 * reproducción que lo sostiene, los eventos de las pantallas reales
 * (`useEventosDemo`) y los trabajos de carga de lote (`useTrabajoFase`). Va
 * dentro de `BrowserRouter`: `ir(n)` navega al destino del paso. `empezar` y
 * `reiniciar` viven en `useArranqueDemo` para
 * no pasar de 9 KB.
 *
 * Un paso se da por hecho de tres maneras (`pasos.ts`): por el evento de la
 * pantalla real, por el fin del trabajo que lanza, o con llegar a su pantalla
 * (`useHechoAlLlegar`, por `pathname`). «Siguiente» está siempre disponible.
 *
 * La navegación entre pasos (`ir`, con su navegación pendiente de datos
 * asíncronos) vive en `useNavegacionPaso`.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";

import { ApiError } from "@/api/client";
import { useAlerts } from "@/api/queries";
import { useGuionDemo } from "@/api/queries-contenido";
import { useReproduccion } from "@/api/queries-demo";
import { fasesReproducidas } from "@/pages/demo/tipos";
import { useSession } from "@/session/session";

import { DemoGuiadaContext, type DemoGuiadaContextValue } from "./contexto";
import { resolverDestino, type ContextoDestino } from "./destino";
import { pasosConEvento } from "./pasos";
import { guardarEstadoDemo, leerEstadoDemo, type EstadoDemo } from "./progreso";
import { useArranqueDemo } from "./useArranqueDemo";
import { useEventosDemo } from "./useEventosDemo";
import { useHechoAlLlegar } from "./useHechoAlLlegar";
import { useNavegacionPaso } from "./useNavegacionPaso";
import { useTrabajoFase } from "./useTrabajoFase";

export function DemoGuiadaProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { projectId: proyectoSesion, setProjectId } = useSession();
  const [estado, setEstado] = useState<EstadoDemo>(leerEstadoDemo);

  useEffect(() => {
    guardarEstadoDemo(estado);
  }, [estado]);

  const contenidoQ = useGuionDemo();
  const contenido = contenidoQ.data;
  const pasos = useMemo(() => contenido?.pasos ?? [], [contenido]);
  const ultimo = Math.max(0, pasos.length - 1);
  const pasoActual = pasos[estado.paso] ?? null;
  const opcional = pasos.find((p) => p.opcional)?.id ?? null;
  const idsConEvento = useMemo(() => pasosConEvento(pasos), [pasos]);

  const runQ = useReproduccion(estado.runId);
  const run = runQ.data ?? null;
  // 404 (reproducción inexistente) es distinto de "aún cargando".
  const runEs404 = runQ.isError && runQ.error instanceof ApiError && runQ.error.status === 404;
  const resultado = useMemo(() => fasesReproducidas(run), [run]);
  const alertasQ = useAlerts(estado.activa ? estado.projectId : null, { monitor_type: "fairness" });

  const ctxDestino: ContextoDestino = useMemo(
    () => ({
      scenarioKey: contenido?.guion.scenario_key ?? "",
      projectId: estado.projectId,
      resultado,
      alertas: alertasQ.data?.items ?? [],
    }),
    [contenido, estado.projectId, resultado, alertasQ.data],
  );
  const destino = useMemo(() => resolverDestino(pasoActual, ctxDestino), [pasoActual, ctxDestino]);

  const marcarHecho = useCallback((n: number) => {
    setEstado((s) => (s.hechos.includes(n) ? s : { ...s, hechos: [...s.hechos, n] }));
  }, []);

  useHechoAlLlegar(pasos, estado, destino, location.pathname, resultado.length, marcarHecho);

  // Un proyecto nuevo no tiene reproducción: se olvida `runId` y se quitan
  // de `hechos` los pasos «subir» y «anotar».
  const fijarProyecto = useCallback(
    (projectId: number) => {
      setEstado((s) => ({
        ...s,
        projectId,
        runId: null,
        hechos: s.hechos.filter((n) => n !== idsConEvento.subir && n !== idsConEvento.anotar),
      }));
      if (proyectoSesion !== projectId) setProjectId(projectId);
    },
    [proyectoSesion, setProjectId, idsConEvento],
  );

  const atado = useEventosDemo({
    runId: estado.runId,
    run,
    runEs404,
    pasos: idsConEvento,
    scenarioKey: contenido?.guion.scenario_key,
    withHuman: contenido?.guion.with_human ?? false,
    alCrearModelo: fijarProyecto,
    alAtar: (runId, projectId) => {
      setEstado((s) => ({ ...s, runId, projectId }));
      if (proyectoSesion !== projectId) setProjectId(projectId);
    },
    marcarHecho,
  });

  const trabajo = useTrabajoFase(estado.runId, marcarHecho);

  const ir = useNavegacionPaso({ pasos, ultimo, opcional, ctxDestino, setEstado });

  const { empezar, reiniciar } = useArranqueDemo({
    ir,
    ctxDestino,
    runIdActual: estado.runId,
    proyectoSesion,
    setProjectId,
    setEstado,
    navigate,
  });

  const value = useMemo<DemoGuiadaContextValue>(
    () => ({
      activa: estado.activa,
      plegado: estado.plegado,
      paso: estado.paso,
      pasoActual,
      pasos,
      contenido,
      run,
      resultado,
      runId: estado.runId,
      projectId: estado.projectId,
      hechos: new Set(estado.hechos),
      opcionalVisto: estado.opcionalVisto,
      completado: estado.completado,
      destino,
      atado,
      trabajo,
      empezar,
      ir,
      // Desde «Fin del caso», «Siguiente» salta el paso opcional; «Anterior»
      // desde el laboratorio vuelve al opcional solo si se visitó.
      siguiente: () => ir(opcional !== null && estado.paso + 1 === opcional ? opcional + 1 : estado.paso + 1),
      anterior: () =>
        ir(opcional !== null && estado.paso - 1 === opcional && !estado.opcionalVisto ? opcional - 1 : estado.paso - 1),
      verOpcional: () => {
        if (opcional !== null) ir(opcional);
      },
      cerrar: () => setEstado((s) => ({ ...s, activa: false })),
      plegar: (plegado: boolean) => setEstado((s) => ({ ...s, plegado })),
      reiniciar,
      marcarHecho,
    }),
    [estado, pasoActual, pasos, contenido, run, resultado, destino, atado, trabajo, empezar, ir, opcional, reiniciar, marcarHecho],
  );

  return <DemoGuiadaContext.Provider value={value}>{children}</DemoGuiadaContext.Provider>;
}
