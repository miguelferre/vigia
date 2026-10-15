/**
 * Tipo de tarea del proyecto y lo que cada pantalla enseña por tipo. Lógica pura, sin React: la usan los `.ts` de los monitores,
 * del alta y de la capa humana. El hook `useTipoTarea()` la compone con el
 * proyecto de la sesión.
 *
 * `CAPACIDADES` lleva una fila por cada valor de `task_type` del OpenAPI. Si el
 * esquema gana otro tipo, `tsc` falla hasta que alguien añada su fila.
 *
 * `claveClase` es el único normalizador de clases del frontend: copia
 * `clave_clase` de `core/schema.py`. Las medidas por clase (`group_code =
 * "clase:<clave>"`), `details.por_clase`, `by_class` de la deriva y el diario
 * de uso se indexan con esa clave; un normalizador propio no casaría.
 */

import type { AyudaMetrica } from "@/api/queries-contenido";
import type { ProjectDetail, ProjectListItem } from "@/api/types";

/** `Project.task_type`, derivado del esquema generado. */
export type TipoTarea = ProjectDetail["task_type"];

/** Una clase tal como la declara el proyecto (`classes`). */
export type Clase = number | string;

export interface CapacidadesTarea {
  /** Matriz de confusión de Calidad: `2x2` (tp/fp/fn/tn), `kxk`
   * (`details.confusion_matrix`) o ninguna. */
  matriz: "2x2" | "kxk" | null;
  /** Tabla por clase (precisión, recall, F1, soporte) en Calidad y la
   * tabla plegada de Equidad. */
  tablaPorClase: boolean;
  /** Histograma de confianza de Deriva: `binaria` (clase 1 y 0, `[0,5; 1]`),
   * `por_clase` (`k` clases, `[1/k; 1]`) o ninguna. */
  confianza: "binaria" | "por_clase" | null;
  /** Resultado bueno: un valor (`uno`), un conjunto de clases (`conjunto`)
   * o ninguno (sin equidad por favorable). */
  favorables: "uno" | "conjunto" | null;
  /** Salida del modelo: una probabilidad (`escalar`), `k` probabilidades
   * (`vector`) o ninguna. */
  probabilidad: "escalar" | "vector" | null;
  /** Explicabilidad con selector de clase. */
  selectorClaseExplicacion: boolean;
  /** Decisión del profesional en la capa humana: `refer`/`no-refer`,
   * nombres de clase o cifras con la pertenencia al rango
   * favorable como decisión derivada. */
  decisionHumana: "derivacion" | "clases" | "rango";
  /** Bloque de `metricas-ayuda.json` que leen las ayudas. */
  bloqueAyuda: "base" | "multiclase" | "regresion";
  /** Familia de métricas de calidad: aciertos de clase (`clasificacion`) o
   * error en la unidad de la salida (`regresion`: MAE, RMSE, R², sesgo). */
  metricas: "clasificacion" | "regresion";
  /** La salida tiene unidad (`target_unit`) y los valores de error la
   * llevan. */
  unidad: boolean;
  /** El proyecto puede declarar un rango favorable de 1 a 3 intervalos
   * */
  rangoFavorable: boolean;
  /** Cuándo existe la capa humana: siempre, o solo con rango favorable
   * */
  capaHumana: "siempre" | "con_rango";
  /** El alta ofrece el modelo simulado de la demo; la regresión no lo tiene
   * (el backend da 422). */
  modeloSimulado: boolean;
  /** El alta ofrece «Ejecutable» (ONNX) como tipo de modelo. */
  ofreceEjecutable: boolean;
}

/**
 * Mapa de capacidades por tipo. Las pantallas deciden
 * con estas claves; un tipo nuevo sin fila hace fallar `tsc`.
 */
export const CAPACIDADES = {
  binary: {
    matriz: "2x2",
    tablaPorClase: false,
    confianza: "binaria",
    favorables: "uno",
    probabilidad: "escalar",
    selectorClaseExplicacion: false,
    decisionHumana: "derivacion",
    bloqueAyuda: "base",
    metricas: "clasificacion",
    unidad: false,
    rangoFavorable: false,
    capaHumana: "siempre",
    modeloSimulado: true,
    ofreceEjecutable: false,
  },
  multiclass: {
    matriz: "kxk",
    tablaPorClase: true,
    confianza: "por_clase",
    favorables: "conjunto",
    probabilidad: "vector",
    selectorClaseExplicacion: true,
    decisionHumana: "clases",
    bloqueAyuda: "multiclase",
    metricas: "clasificacion",
    unidad: false,
    rangoFavorable: false,
    capaHumana: "siempre",
    modeloSimulado: true,
    ofreceEjecutable: false,
  },
  regression: {
    matriz: null,
    tablaPorClase: false,
    confianza: null,
    favorables: null,
    probabilidad: null,
    selectorClaseExplicacion: false,
    decisionHumana: "rango",
    bloqueAyuda: "regresion",
    metricas: "regresion",
    unidad: true,
    rangoFavorable: true,
    capaHumana: "con_rango",
    modeloSimulado: false,
    ofreceEjecutable: true,
  },
} as const satisfies Record<TipoTarea, CapacidadesTarea>;

export function capacidades(tipo: TipoTarea): CapacidadesTarea {
  return CAPACIDADES[tipo];
}

/** Copia de `clave_clase` (`core/schema.py`): espacios recortados; un
 * decimal entero (`1.0`) vale lo mismo que el entero (`"1"`). No cambia
 * mayúsculas. */
export function claveClase(valor: Clase | boolean): string {
  if (typeof valor === "boolean") return valor ? "1" : "0";
  if (typeof valor === "number") {
    return Number.isInteger(valor) ? String(Math.trunc(valor)) : String(valor);
  }
  return valor.trim();
}

export const PREFIJO_GRUPO_CLASE = "clase:";

/** `group_code` de una medida por clase (`grupo_clase` del backend). */
export function grupoClase(valor: Clase): string {
  return `${PREFIJO_GRUPO_CLASE}${claveClase(valor)}`;
}

export function esGrupoClase(groupCode: string | null | undefined): boolean {
  return !!groupCode && groupCode.startsWith(PREFIJO_GRUPO_CLASE);
}

/** Clase de un `group_code` por clase, o `null` si no es por clase. */
export function claseDeGrupo(groupCode: string | null | undefined): string | null {
  return esGrupoClase(groupCode) ? groupCode!.slice(PREFIJO_GRUPO_CLASE.length) : null;
}

/** `favorable_label` como lista de claves: un valor suelto es una lista de
 * uno; `null`, vacío o ausente es la lista vacía (sin conjunto favorable). */
export function favorablesComoLista(favorable: Clase | Clase[] | null | undefined): string[] {
  if (favorable === null || favorable === undefined) return [];
  const lista = Array.isArray(favorable) ? favorable : [favorable];
  return lista.map(claveClase);
}

type ProyectoConClases = Pick<ProjectListItem, "task_type" | "classes" | "favorable_label">;

/** Clases del proyecto como claves, en el orden declarado. El backend ya
 * resuelve `classes_json` y, antes de la línea base, las de la plantilla. En
 * binario sin clases declaradas, la lista vacía. */
export function clasesDelProyecto(p: ProyectoConClases): string[] {
  return (p.classes ?? []).map(claveClase);
}

/** Conjunto favorable del proyecto como claves (lo resuelve la API
 * desde la plantilla). */
export function favorablesDelProyecto(p: ProyectoConClases): string[] {
  return favorablesComoLista(p.favorable_label);
}

/**
 * Ayuda de una métrica según el tipo de tarea. El bloque que pide `caps.bloqueAyuda` (`multiclase` o `regresion`)
 * pisa los campos de la entrada: un campo nulo hereda el de la entrada;
 * `formula_vars: []` sustituye (la fórmula no se instancia con números);
 * `umbral_por_defecto: {}` quita el umbral (el umbral sale de la línea base).
 * En binario, o sin bloque, la entrada tal cual. El
 * resultado no lleva los bloques.
 */
export function ayudaPorTipo(entrada: AyudaMetrica, tipo: TipoTarea | undefined): AyudaMetrica {
  const bloque = bloqueDeAyuda(entrada, tipo);
  if (!bloque) return entrada;
  const umbral = bloque.umbral_por_defecto;
  return {
    ...entrada,
    que_mide: bloque.que_mide ?? entrada.que_mide,
    como_se_lee: bloque.como_se_lee ?? entrada.como_se_lee,
    formula: bloque.formula ?? entrada.formula,
    formula_vars: bloque.formula_vars ?? entrada.formula_vars,
    umbral_por_defecto:
      umbral === null ? entrada.umbral_por_defecto : Object.keys(umbral).length === 0 ? null : umbral,
    multiclase: null,
    regresion: null,
  };
}

function bloqueDeAyuda(entrada: AyudaMetrica, tipo: TipoTarea | undefined) {
  if (tipo === undefined) return null;
  const bloque = CAPACIDADES[tipo].bloqueAyuda;
  switch (bloque) {
    case "base":
      return null;
    case "multiclase":
      return entrada.multiclase ?? null;
    case "regresion":
      return entrada.regresion ?? null;
    default: {
      const _exhaustivo: never = bloque;
      throw new Error(`bloque de ayuda no reconocido: ${String(_exhaustivo)}`);
    }
  }
}
