import { formatoCorto } from "@/lib/metrics";

/**
 * Valor de un grupo tal como llega en `group_context.supervised`/`.reference`
 * (texto de `_group_labels`, `src/vigia/app/services/projects.py`): un rango
 * `[a, b]` ya viene unido como `"a-b"`, pero con los `.0` de los `float` de
 * Python; el resto de valores (categóricos) llega tal cual y no debe tocarse.
 * Fichero propio (sin componentes) para que `contexto-grupos.tsx` solo exporte
 * componentes y hooks (react-refresh).
 */
export function formatoEtiquetaGrupo(etiqueta: string): string {
  const rango = /^(-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?)$/.exec(etiqueta);
  if (!rango) return etiqueta;
  return `${formatoCorto(Number(rango[1]))}-${formatoCorto(Number(rango[2]))}`;
}

