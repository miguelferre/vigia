/**
 * Test de tipos de `tipo-tarea.ts`. No se ejecuta: lo comprueba
 * `npx tsc -p tsconfig.app.json --noEmit`. Si el esquema gana un tipo de
 * tarea sin fila en `CAPACIDADES`, o la fila sobra, `tsc` falla aquí.
 */

import { CAPACIDADES, type CapacidadesTarea, type TipoTarea } from "./tipo-tarea";

type Igual<A, B> = (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;
type Afirmar<T extends true> = T;

// Las claves del mapa son exactamente los valores de `task_type` del OpenAPI.
export type _ClavesExactas = Afirmar<Igual<keyof typeof CAPACIDADES, TipoTarea>>;

// Hoy el OpenAPI declara los tres tipos de tarea.
export type _TiposDeC11 = Afirmar<Igual<TipoTarea, "binary" | "multiclass" | "regression">>;

// Cada fila cumple la forma completa.
export const _filas: Record<TipoTarea, CapacidadesTarea> = CAPACIDADES;

// Binario no cambia: matriz 2x2, una favorable, probabilidad escalar.
export type _Binario = Afirmar<
  Igual<
    Pick<(typeof CAPACIDADES)["binary"], "matriz" | "favorables" | "probabilidad">,
    { readonly matriz: "2x2"; readonly favorables: "uno"; readonly probabilidad: "escalar" }
  >
>;

// `ayudaPorTipo` devuelve la misma forma que la entrada.
import type { AyudaMetrica } from "@/api/queries-contenido";
import type { ayudaPorTipo } from "./tipo-tarea";
export type _Ayuda = Afirmar<Igual<ReturnType<typeof ayudaPorTipo>, AyudaMetrica>>;
