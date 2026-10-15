/**
 * `useContenidoMetricas` y `useGlosario`, sobre `GET /api/content/metricas` y
 * `GET /api/content/glosario`. Mismo patrón de
 * partido que `queries-timeline.ts` y `queries-datos.ts`.
 * Suma `usePresentacion`, `useGuionDemo` y `useGuiaUso` sobre
 * `/content/presentacion`, `/content/demo` y `/content/guia-uso`;
 * `/content/onboarding` y `useGuionOnboarding` desaparecen.
 *
 * `staleTime: Infinity`: es contenido estático dentro de una ejecución, el
 * router no lo cambia sin reiniciar el backend.
 *
 * Los tipos salen del OpenAPI (`npm run api:types`): no se
 * teclean a mano.
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { useTipoTarea } from "@/hooks/useTipoTarea";
import { registrarFasesDemo } from "@/lib/fases";
import { ayudaPorTipo, CAPACIDADES } from "@/lib/tipo-tarea";

import { api } from "./client";
import { type Opciones } from "./queries";
import type { components } from "./schema";

/** Una entrada de `metricas-ayuda.json`: qué mide una métrica y su fórmula. */
export type AyudaMetrica = components["schemas"]["ContenidoMetrica"];

/** Una entrada de `glosario.json`: un concepto no métrico. */
export type EntradaGlosario = components["schemas"]["ContenidoGlosarioTermino"];

export type ContenidoMetricas = Record<string, AyudaMetrica>;
export type Glosario = Record<string, EntradaGlosario>;

const qkContenido = {
  metricas: () => ["content", "metricas"] as const,
  glosario: () => ["content", "glosario"] as const,
  textosPantalla: () => ["content", "textos-pantalla"] as const,
};

/**
 * Textos largos por pantalla y sección (`GET /content/textos-pantalla`):
 * qué se sube, cómo se lee la explicabilidad, qué
 * entra en cada carril del diario. Sin tipo generado propio (el
 * router lo declara `dict[str, dict[str, str]]`): se usa tal cual, tolerante
 * a una sección o clave ausente mientras el contenido crece.
 */
export type TextosPantalla = Record<string, Record<string, string>>;

/** Ayuda larga de una pantalla; puede faltar si el contenido no la incluye. */
export function useTextosPantalla(opciones?: Opciones<TextosPantalla>) {
  return useQuery({
    queryKey: qkContenido.textosPantalla(),
    queryFn: () => api.get<TextosPantalla>("/content/textos-pantalla"),
    staleTime: Infinity,
    ...opciones,
  });
}

/** Ayuda contextual por `metric_key`: qué mide y su fórmula. */
export function useContenidoMetricas(opciones?: Opciones<ContenidoMetricas>) {
  return useQuery({
    queryKey: qkContenido.metricas(),
    queryFn: () => api.get<ContenidoMetricas>("/content/metricas"),
    staleTime: Infinity,
    ...opciones,
  });
}

/**
 * `useContenidoMetricas` con cada entrada resuelta por el tipo de tarea del
 * proyecto (`ayudaPorTipo`): en multiclase pisa `que_mide`,
 * `como_se_lee`, `formula`, `formula_vars` y el umbral por defecto con el
 * bloque `multiclase`; en binario devuelve el mismo objeto de siempre. Sin
 * `projectId`, el proyecto de la sesión. Mientras el proyecto carga, `data`
 * es `undefined` (no se enseña el texto binario a un proyecto multiclase).
 */
export function useContenidoMetricasPorTipo(projectId?: number | null) {
  const q = useContenidoMetricas();
  const { tipo, cargando } = useTipoTarea(projectId);
  const crudo = q.data;
  const data = useMemo<ContenidoMetricas | undefined>(() => {
    if (!crudo) return undefined;
    if (tipo === undefined) return cargando ? undefined : crudo;
    if (CAPACIDADES[tipo].bloqueAyuda === "base") return crudo;
    return Object.fromEntries(Object.entries(crudo).map(([clave, entrada]) => [clave, ayudaPorTipo(entrada, tipo)]));
  }, [crudo, tipo, cargando]);
  return { ...q, data };
}

/** Glosario de conceptos no métricos: grupos, ventana, estados, etc. */
export function useGlosario(opciones?: Opciones<Glosario>) {
  return useQuery({
    queryKey: qkContenido.glosario(),
    queryFn: () => api.get<Glosario>("/content/glosario"),
    staleTime: Infinity,
    ...opciones,
  });
}

/** Una diapositiva de `presentacion.json`. */
export type Diapositiva = components["schemas"]["PresentacionDiapositiva"];

/** `GET /content/presentacion`: las 11 diapositivas. */
export type ContenidoPresentacion = components["schemas"]["ContenidoPresentacion"];

/** Un paso de `demo-digestivo.json` (`tipo` "paso" o "diapositiva"). */
export type PasoDemo = components["schemas"]["DemoPaso"];

/** Un control del laboratorio: etiqueta, rango y paso desde el contenido. */
export type ParametroLaboratorio = components["schemas"]["LaboratorioParametro"];

/** `GET /content/demo`: guion, fases, 22 pasos, laboratorio, dominio y cierre. */
export type ContenidoDemo = components["schemas"]["ContenidoDemo"];

/** Una entrada de `guia-uso.json` (12, para `/ayuda#guia`). */
export type EntradaGuia = components["schemas"]["GuiaUsoEntrada"];

/** `GET /content/guia-uso`: las 12 entradas de la guía de uso. */
export type ContenidoGuiaUso = components["schemas"]["ContenidoGuiaUso"];

/** `GET /content/guia-datos`: qué ficheros pide Vigía y cómo, con sus plantillas. */
export type GuiaDatos = components["schemas"]["GuiaDatos"];
export type GuiaDatosSeccion = components["schemas"]["GuiaDatosSeccion"];
export type GuiaDatosColumna = components["schemas"]["GuiaDatosColumna"];

const qkUi4 = {
  guiaDatos: () => ["content", "guia-datos"] as const,
  presentacion: () => ["content", "presentacion"] as const,
  demo: () => ["content", "demo"] as const,
  guiaUso: () => ["content", "guia-uso"] as const,
};

/** Guía de datos de `/ayuda#datos`. */
export function useGuiaDatos(opciones?: Opciones<GuiaDatos>) {
  return useQuery({
    queryKey: qkUi4.guiaDatos(),
    queryFn: () => api.get<GuiaDatos>("/content/guia-datos"),
    staleTime: Infinity,
    ...opciones,
  });
}

/** Guion de la presentación (`/demo`). */
export function usePresentacion(opciones?: Opciones<ContenidoPresentacion>) {
  return useQuery({
    queryKey: qkUi4.presentacion(),
    queryFn: () => api.get<ContenidoPresentacion>("/content/presentacion"),
    staleTime: Infinity,
    ...opciones,
  });
}

/**
 * Guion de la demo guiada del caso Digestivo. Al llegar registra `fases` en
 * `lib/fases.ts`: `etiquetaLote()` sigue siendo una función pura y
 * traduce `b1`, `e1_evento`, `e1_recovery` y `lab:*` con estas etiquetas en
 * cuanto el contenido está cargado; hasta entonces cae a su regex.
 * `dominio` es el diccionario de nombres clínicos que antes servía
 * `/content/onboarding`.
 */
export function useGuionDemo(opciones?: Opciones<ContenidoDemo>) {
  return useQuery({
    queryKey: qkUi4.demo(),
    queryFn: async () => {
      const contenido = await api.get<ContenidoDemo>("/content/demo");
      registrarFasesDemo(contenido.fases);
      return contenido;
    },
    staleTime: Infinity,
    ...opciones,
  });
}

/** Guía de uso: las 12 entradas de `/ayuda#guia`. */
export function useGuiaUso(opciones?: Opciones<ContenidoGuiaUso>) {
  return useQuery({
    queryKey: qkUi4.guiaUso(),
    queryFn: () => api.get<ContenidoGuiaUso>("/content/guia-uso"),
    staleTime: Infinity,
    ...opciones,
  });
}
