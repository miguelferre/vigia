/**
 * Tipo de tarea del proyecto de la sesión y sus capacidades. Las pantallas deciden qué enseñar con `caps`, nunca preguntando
 * por `task_type` suelto.
 *
 * Mientras el proyecto carga, `tipo` y `caps` son `undefined`: el componente
 * que depende de ellos espera (no dibuja binario por defecto, para que un
 * proyecto multiclase no parpadee de 2x2 a k x k).
 *
 * Sin argumento lee el proyecto de la sesión; con `projectId` lee ese.
 */

import { useProject } from "@/api/queries";
import {
  capacidades,
  clasesDelProyecto,
  favorablesDelProyecto,
  type CapacidadesTarea,
  type TipoTarea,
} from "@/lib/tipo-tarea";
import type { RangoFavorable } from "@/lib/metrics";
import { useSession } from "@/session/session";

export interface EstadoTipoTarea {
  /** `undefined` mientras carga o sin proyecto. */
  tipo: TipoTarea | undefined;
  /** Lo que la pantalla enseña por tipo: no hay un booleano de
   * «es multiclase»; una pregunta por el tipo suelto dejaba caer la regresión
   * al binario. */
  caps: CapacidadesTarea | undefined;
  /** Clases declaradas como claves (`claveClase`), en el orden del proyecto. */
  clases: string[];
  /** Conjunto favorable como claves; vacío si no hay. */
  favorables: string[];
  /** `true` si la clave está en el conjunto favorable. */
  esFavorable: (clave: string) => boolean;
  /** Unidad de la salida en regresión (`target_unit`); `null` en
   * clasificación o sin unidad. */
  unidad: string | null;
  /** Rango favorable de la regresión; vacío sin rango o en clasificación
   * */
  rangos: RangoFavorable[];
  /** `true` en una regresión sin rango favorable: la capa humana y las
   * medidas de pertenencia no aplican. */
  sinRango: boolean;
  cargando: boolean;
}

export function useTipoTarea(projectId?: number | null): EstadoTipoTarea {
  const sesion = useSession();
  const id = projectId === undefined ? sesion.projectId : projectId;
  const q = useProject(id);
  const p = q.data;
  const tipo = p?.task_type;
  const clases = p ? clasesDelProyecto(p) : [];
  const favorables = p ? favorablesDelProyecto(p) : [];
  const caps = tipo ? capacidades(tipo) : undefined;
  const rangos: RangoFavorable[] = caps?.rangoFavorable ? (p?.favorable_ranges ?? []) : [];
  return {
    tipo,
    caps,
    clases,
    favorables,
    esFavorable: (clave) => favorables.includes(clave),
    unidad: caps?.unidad ? (p?.target_unit ?? null) : null,
    rangos,
    sinRango: !!caps?.rangoFavorable && rangos.length === 0,
    cargando: q.isPending && id !== null,
  };
}
