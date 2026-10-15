/**
 * Agrupación y filtro de `/ayuda`: glosario por prefijo de clave (estados,
 * grupos y ventana, monitores, carriles, otros), métricas por `monitor`
 * (equidad, calidad, deriva, reglas cruzadas, explicabilidad) y guía de uso por título,
 * propósito y pasos. Funciones puras, sin React, para
 * poder probarlas sueltas.
 */

import type { Glosario, EntradaGlosario, ContenidoMetricas, EntradaGuia } from "@/api/queries-contenido";
import type { MonitorType } from "@/api/types";
import type { AyudaMetricaAmpliada } from "./tipos";

export type NombreGrupoGlosario = "Estados" | "Grupos y ventana" | "Monitores" | "Carriles" | "Otros";

const ORDEN_GRUPOS_GLOSARIO: readonly NombreGrupoGlosario[] = [
  "Estados",
  "Grupos y ventana",
  "Monitores",
  "Carriles",
  "Otros",
];

const CLAVES_VENTANA = new Set(["ventana", "intervalo", "muestra_minima"]);

function grupoDeClave(clave: string): NombreGrupoGlosario {
  // `estado_despliegue` es del proyecto, no del motor: va con «Otros».
  if (clave === "estado_despliegue") return "Otros";
  if (clave.startsWith("estado_")) return "Estados";
  if (clave.startsWith("grupo_") || CLAVES_VENTANA.has(clave)) return "Grupos y ventana";
  if (clave.startsWith("monitor_")) return "Monitores";
  if (clave.startsWith("carril_")) return "Carriles";
  return "Otros";
}

function coincide(busqueda: string, ...campos: Array<string | null | undefined>): boolean {
  const termino = busqueda.trim().toLocaleLowerCase("es-ES");
  if (!termino) return true;
  return campos.some((campo) => (campo ?? "").toLocaleLowerCase("es-ES").includes(termino));
}

export interface GrupoGlosario {
  nombre: NombreGrupoGlosario;
  entradas: Array<[string, EntradaGlosario]>;
}

export function agruparGlosario(glosario: Glosario | undefined, busqueda: string): GrupoGlosario[] {
  const porGrupo = new Map<NombreGrupoGlosario, Array<[string, EntradaGlosario]>>();
  for (const [clave, entrada] of Object.entries(glosario ?? {})) {
    if (!coincide(busqueda, entrada.etiqueta, entrada.definicion, clave)) continue;
    const lista = porGrupo.get(grupoDeClave(clave)) ?? [];
    lista.push([clave, entrada]);
    porGrupo.set(grupoDeClave(clave), lista);
  }
  return ORDEN_GRUPOS_GLOSARIO.filter((nombre) => porGrupo.has(nombre)).map((nombre) => ({
    nombre,
    entradas: [...(porGrupo.get(nombre) ?? [])].sort((a, b) => a[1].etiqueta.localeCompare(b[1].etiqueta, "es")),
  }));
}

const ORDEN_MONITORES: readonly MonitorType[] = ["fairness", "quality", "drift", "cross", "explain"];

export interface GrupoMetricas {
  monitor: MonitorType;
  entradas: Array<[string, AyudaMetricaAmpliada]>;
}

export function agruparMetricas(metricas: ContenidoMetricas | undefined, busqueda: string): GrupoMetricas[] {
  const porMonitor = new Map<MonitorType, Array<[string, AyudaMetricaAmpliada]>>();
  for (const [clave, entradaBase] of Object.entries(metricas ?? {})) {
    const entrada = entradaBase as AyudaMetricaAmpliada;
    if (!coincide(busqueda, entrada.etiqueta, entrada.que_mide, clave)) continue;
    const lista = porMonitor.get(entrada.monitor) ?? [];
    lista.push([clave, entrada]);
    porMonitor.set(entrada.monitor, lista);
  }
  return ORDEN_MONITORES.filter((monitor) => porMonitor.has(monitor)).map((monitor) => ({
    monitor,
    // Las reglas cruzadas van por número (CX-1 a CX-6), no por etiqueta.
    entradas: [...(porMonitor.get(monitor) ?? [])].sort((a, b) =>
      monitor === "cross"
        ? a[0].localeCompare(b[0], "es", { numeric: true })
        : a[1].etiqueta.localeCompare(b[1].etiqueta, "es"),
    ),
  }));
}

/** Entradas de la guía de uso cuyo título, propósito o algún paso coinciden con `busqueda`. */
export function filtrarGuia(entradas: EntradaGuia[] | undefined, busqueda: string): EntradaGuia[] {
  return (entradas ?? []).filter((entrada) =>
    coincide(busqueda, entrada.titulo, entrada.para_que, ...entrada.pasos),
  );
}
