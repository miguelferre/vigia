/**
 * Nota del paso «Umbrales» que depende del tipo de tarea: en multiclase
 * y en regresión los umbrales salen de la línea base. Un
 * `switch` sobre `caps.bloqueAyuda` sin `default` abierto.
 */

import type { ProjectDetail } from "@/api/types";
import { capacidades } from "@/lib/tipo-tarea";

import { TEXTO_UMBRALES_MULTICLASE, textoUmbralesRegresion } from "./alta-umbrales-textos";

export function NotaUmbralesTipo({ proyecto }: { proyecto: Pick<ProjectDetail, "task_type" | "target_unit"> | undefined }) {
  if (!proyecto) return null;
  const bloque = capacidades(proyecto.task_type).bloqueAyuda;
  switch (bloque) {
    case "base":
      return null;
    case "multiclase":
      return (
        <p className="text-sm text-muted-foreground" data-testid="umbrales-multiclase">
          {TEXTO_UMBRALES_MULTICLASE}
        </p>
      );
    case "regresion":
      return (
        <p className="text-sm text-muted-foreground" data-testid="umbrales-regresion">
          {textoUmbralesRegresion(proyecto.target_unit)}
        </p>
      );
    default: {
      const _exhaustivo: never = bloque;
      throw new Error(`bloque de ayuda no reconocido: ${String(_exhaustivo)}`);
    }
  }
}
