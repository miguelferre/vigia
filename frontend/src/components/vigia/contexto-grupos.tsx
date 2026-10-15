/**
 * Contexto de grupos supervisado/referencia, partido de
 * `DrillImpactoDispar.tsx` porque el Context y sus
 * hooks generaban avisos de `react-refresh/only-export-components` en un
 * fichero que también exporta el componente `DrillImpactoDispar`.
 *
 * Vocabulario: nunca "unpriv"/"priv" en texto visible,
 * siempre "grupo supervisado" y "grupo de referencia"; `nombreSupervisado`/
 * `nombreReferencia` degradan a esos términos genéricos si no hay contexto
 * (alerta, laboratorio) o si `group_context` es `null`.
 */

import { createContext, useContext, type ReactNode } from "react";

import type { GroupContext } from "@/api/types-domain";
import { nombreVariable } from "@/lib/dominio-caracteristicas";
import { formatoEtiquetaGrupo } from "./formato-grupo";

export const ETIQUETA_SUPERVISADO = "grupo supervisado";
export const ETIQUETA_REFERENCIA = "grupo de referencia";

const Contexto = createContext<GroupContext>(null);

export function GroupContextProvider({
  value,
  children,
}: {
  value: GroupContext;
  children: ReactNode;
}) {
  return <Contexto.Provider value={value}>{children}</Contexto.Provider>;
}

export function useGroupContext(): GroupContext {
  return useContext(Contexto);
}

/**
 * Etiqueta de grupo ya formateada: atributo por `nombreVariable` (dominio
 * clínico si lo hay) y valores por `formatoEtiquetaGrupo` (sin los `.0` de
 * un rango). `dominio` es opcional: sin él (o sin contenido cargado
 * todavía) se usa el nombre técnico del atributo, nunca vacío.
 */
export function nombreSupervisado(ctx: GroupContext, dominio?: Record<string, string>): string {
  if (!ctx || ctx.supervised.length === 0) return ETIQUETA_SUPERVISADO;
  const atributo = nombreVariable(ctx.protected_attr, dominio);
  return `${atributo} = ${ctx.supervised.map(formatoEtiquetaGrupo).join(", ")}`;
}

export function nombreReferencia(ctx: GroupContext, dominio?: Record<string, string>): string {
  if (!ctx || ctx.reference.length === 0) return ETIQUETA_REFERENCIA;
  const atributo = nombreVariable(ctx.protected_attr, dominio);
  return `${atributo} = ${ctx.reference.map(formatoEtiquetaGrupo).join(", ")}`;
}
