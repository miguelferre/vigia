/**
 * Navegación entre pasos de la demo guiada, separada de `Provider.tsx`. `ir(n)` fija el paso y navega al destino.
 *
 * Si `ir(n)` no puede navegar porque el destino depende de un dato que aún
 * no ha llegado (la alerta de los pasos 21 y 22, el lote del 18: la lista de
 * alertas solo se pide con la demo activa y la reproducción recién adoptada
 * por `?run=` tarda un render en cargar), el paso queda pendiente de
 * navegación y un efecto navega en cuanto `destino` se resuelve, siempre que
 * el paso siga siendo ese y el usuario no haya cambiado de ruta entre medias.
 */

import { useCallback, useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useLocation, useNavigate } from "react-router";

import type { PasoDemo } from "@/api/queries-contenido";

import { programarScrollAAncla, resolverDestino, type ContextoDestino } from "./destino";
import type { EstadoDemo } from "./progreso";

interface Params {
  pasos: PasoDemo[];
  ultimo: number;
  opcional: number | null;
  ctxDestino: ContextoDestino;
  setEstado: Dispatch<SetStateAction<EstadoDemo>>;
}

export function useNavegacionPaso({ pasos, ultimo, opcional, ctxDestino, setEstado }: Params) {
  const navigate = useNavigate();
  const location = useLocation();

  const irA = useCallback(
    (href: string, ancla: string | null) => {
      programarScrollAAncla(ancla);
      // Ya en el destino (activación por `?paso=N` desde `/demo`): no se
      // apila una entrada de historial igual a la actual.
      if (href !== `${location.pathname}${location.search}${location.hash}`) navigate(href);
    },
    [navigate, location],
  );

  // Paso cuya navegación quedó pendiente de un dato asíncrono, con la ruta
  // desde la que se pidió: si el usuario se va a otra, se olvida; si pide
  // otro paso, `ir()` lo sustituye. Es un ref (no estado) porque solo lo lee
  // el efecto que navega. El efecto resuelve el destino del paso pendiente
  // por su cuenta, con el contexto fresco, en vez de leer `destino` o
  // `estado.paso`: entre `ir()` y el render con el paso nuevo puede colarse
  // una pasada del efecto con el estado anterior (visto en vivo al activar
  // el 17 por URL con la demo ya en el 14), y comparar contra ese estado
  // descartaba el pendiente antes de tiempo.
  const pendiente = useRef<{ paso: number; desde: string } | null>(null);
  useEffect(() => {
    const p = pendiente.current;
    if (!p) return;
    if (p.desde !== location.pathname) {
      pendiente.current = null;
      return;
    }
    const d = resolverDestino(pasos[p.paso] ?? null, ctxDestino);
    if (d.href === null) return;
    pendiente.current = null;
    irA(d.href, d.ancla);
  }, [pasos, ctxDestino, location.pathname, irA]);

  // `ctx` permite resolver el destino con un proyecto que el estado aún no
  // tiene (`empezar` con `?run=`): el `setEstado` aún no se ha aplicado.
  const ir = useCallback(
    (n: number, ctx: ContextoDestino = ctxDestino) => {
      const objetivo = Math.max(0, Math.min(ultimo, n));
      setEstado((s) => ({
        ...s,
        activa: true,
        paso: objetivo,
        // Sin guion cargado `ultimo` es 0: no hay demo completada.
        completado: s.completado || (pasos.length > 0 && objetivo === ultimo),
        opcionalVisto: s.opcionalVisto || objetivo === opcional,
      }));
      const d = resolverDestino(pasos[objetivo] ?? null, ctx);
      if (d.href) {
        pendiente.current = null;
        irA(d.href, d.ancla);
      } else {
        pendiente.current =
          d.falta === "alerta" || d.falta === "lote" ? { paso: objetivo, desde: location.pathname } : null;
      }
    },
    [ultimo, opcional, pasos, ctxDestino, setEstado, irA, location.pathname],
  );

  return ir;
}
