/**
 * Forma única de "Cómo se ha calculado" en toda métrica con `formula` en
 * `metricas-ayuda.json`: arriba la fórmula
 * simbólica en formato de fórmula, debajo la línea instanciada con las
 * cifras, el resultado destacado y la fila de estado con el umbral. Fichero
 * propio: `CalculoFormula.tsx` (que la consume desde `FormulaInstanciada` y
 * `EscalaCociente`) ya rozaba los 9 KB.
 */

import type { ReactNode } from "react";

import type { EstadoMotor } from "@/api/types";

import { StateBadge } from "./StateBadge";
import type { InfoTooltipProps } from "./InfoTooltip";
import { InfoTooltip } from "./InfoTooltip";

/**
 * La fórmula, dentro de su caja: con "=", la parte izquierda en negrita y el
 * resto (con el "=") en cifras tabulares; sin "=" (una frase, como la de
 * `explain_stability_ndcg` o `confidence_drift_score`), párrafo simple. Misma
 * caja en los dos casos (fondo, borde, `text-md`).
 */
function FormulaSimbolica({ formula }: { formula: string }) {
  if (!formula) return null;
  const pos = formula.indexOf("=");
  if (pos === -1) {
    return <p className="rounded-md border bg-muted/30 p-2 text-md">{formula}</p>;
  }
  const izquierda = formula.slice(0, pos).trim();
  const derecha = formula.slice(pos).trim();
  return (
    <p className="rounded-md border bg-muted/30 p-2 text-md">
      <span className="font-semibold">{izquierda}</span> <span className="tabular-nums">{derecha}</span>
    </p>
  );
}

export interface CajaFormulaProps {
  /** Fórmula simbólica, tal como la trae `metricas-ayuda.json`. */
  formula: string;
  /** Línea con las cifras reales sustituidas, a tamaño normal (color muted). */
  instanciada?: ReactNode;
  /** Resultado ya formateado, destacado. */
  resultado: ReactNode;
  /** Nombre de la métrica, delante del resultado ("nombre = valor"); sin etiqueta si se omite. */
  resultadoEtiqueta?: string;
  /** «Umbral: mínimo X» / «máximo Y» (los dos si hay ambos); `null` sin umbral configurado. */
  umbralTexto: string | null;
  estado: EstadoMotor | null | undefined;
  /** Nota del motor cuando el cálculo es parcial o estimado. */
  motivo?: string | null;
  /** ⓘ opcional junto al resultado (`EscalaCociente` perdió el de `fairness_value`). */
  info?: InfoTooltipProps;
  /** Contenido bajo la fila de estado (por ejemplo la barra de escala del impacto dispar). */
  children?: ReactNode;
}

export function CajaFormula({
  formula,
  instanciada,
  resultado,
  resultadoEtiqueta,
  umbralTexto,
  estado,
  motivo,
  info,
  children,
}: CajaFormulaProps) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border p-3">
      <FormulaSimbolica formula={formula} />
      {instanciada ? <p className="text-md text-muted-foreground">{instanciada}</p> : null}
      <p className="inline-flex items-center gap-1.5 text-lg font-semibold tabular-nums">
        {resultadoEtiqueta ? `${resultadoEtiqueta} = ` : null}
        {resultado}
        {info ? <InfoTooltip {...info} /> : null}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <StateBadge estado={estado} size="sm" />
        {umbralTexto ? <span className="text-md font-semibold">{umbralTexto}</span> : null}
      </div>
      {motivo ? <p className="text-xs text-muted-foreground">{motivo}</p> : null}
      {children}
    </div>
  );
}

export default CajaFormula;
