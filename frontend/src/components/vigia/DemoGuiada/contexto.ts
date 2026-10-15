/**
 * Contexto de la demo guiada (`AtadoDemo.hecho` incluido): lo que el panel acoplado, `/demo` y quien
 * quiera saber si hay una demo en curso leen de `DemoGuiadaProvider`. El
 * tipo vive aparte del proveedor para que los consumidores importen solo
 * el hook.
 */

import { createContext, useContext } from "react";

import type { ContenidoDemo, PasoDemo } from "@/api/queries-contenido";
import type { ActorBody, DemoRun } from "@/api/types";
import type { FaseResumen } from "@/pages/demo/tipos";

import type { DestinoResuelto } from "./destino";

export interface AtadoDemo {
  /** `POST /demo/runs` con `project_id` en vuelo: «Fijando la línea base y cargando las semanas 2 a 5…». */
  enCurso: boolean;
  /** Atado bien hace poco: «Cinco semanas de línea base evaluadas» unos segundos. */
  hecho: boolean;
  error: string | null;
  reintentar: () => void;
}

export interface TrabajoFase {
  /** Un `next` (pasos 11 y 24) encolado y sin terminar. */
  enCurso: boolean;
  progreso: number;
  mensaje: string;
  /** Paso desde el que se lanzó el trabajo en curso o el último terminado. */
  pasoLanzado: number | null;
  lanzar: (paso: number) => Promise<void>;
}

export interface DemoGuiadaContextValue {
  activa: boolean;
  plegado: boolean;
  paso: number;
  pasoActual: PasoDemo | null;
  pasos: PasoDemo[];
  contenido: ContenidoDemo | undefined;
  run: DemoRun | null;
  resultado: FaseResumen[];
  runId: number | null;
  projectId: number | null;
  hechos: ReadonlySet<number>;
  opcionalVisto: boolean;
  completado: boolean;
  /** Destino del paso actual, ya resuelto contra proyecto, lote y alerta. */
  destino: DestinoResuelto;
  atado: AtadoDemo;
  trabajo: TrabajoFase;
  /** Activa la demo en `paso` (0 por defecto), adoptando una reproducción si se pasa. */
  empezar: (paso?: number, runId?: number | null, projectId?: number | null) => void;
  /** Va al paso `n` y navega a su destino. */
  ir: (n: number) => void;
  siguiente: () => void;
  anterior: () => void;
  /**
   * Va al paso marcado `opcional` en el guion, si lo hay. Ahora
   * el guion no tiene ninguno («Tras las medidas» salió) y no lo llama nadie;
   * se conserva por si un guion futuro vuelve a declarar uno.
   */
  verOpcional: () => void;
  /** Oculta el panel sin borrar el estado: `/demo` ofrece «Continuar». */
  cerrar: () => void;
  plegar: (plegado: boolean) => void;
  /** `POST /demo/runs/{id}/reset` si hay reproducción, borra el estado y vuelve a `/demo`. */
  reiniciar: (cuerpo: ActorBody) => Promise<void>;
  marcarHecho: (n: number) => void;
}

export const DemoGuiadaContext = createContext<DemoGuiadaContextValue | null>(null);

/** Estado y acciones de la demo guiada. Exige `DemoGuiadaProvider` por encima. */
export function useDemoGuiada(): DemoGuiadaContextValue {
  const ctx = useContext(DemoGuiadaContext);
  if (!ctx) throw new Error("useDemoGuiada debe usarse dentro de DemoGuiadaProvider");
  return ctx;
}
