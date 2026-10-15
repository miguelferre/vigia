/**
 * Lo que cambia en el detalle de una explicación de regresión: las
 * importancias y las contribuciones van en la unidad de la salida, la local
 * enseña el valor predicho y los colores de las contribuciones no juzgan
 * (subir o bajar el valor predicho no es bueno ni malo). Aparte de
 * `detalle.tsx` por el límite de 9 KB.
 */

import type { ComponentType } from "react";

import type { ExplanationKind, JsonObject } from "@/api/types";
import { formatoMetrica } from "@/lib/metrics";

interface Fila {
  feature: string;
  valor: number;
  rule: string | null;
}

/** Importancia sin signo en la unidad de la salida (misma regla de decimales que el MAE). */
export const formatoImportancia = (valor: number, unidad: string | null) => formatoMetrica("mean_absolute_error", valor, unidad);
/** Contribución con signo en la unidad de la salida (misma regla que el sesgo medio). */
export const formatoContribucion = (valor: number, unidad: string | null) => formatoMetrica("mean_error", valor, unidad);

/** Título del eje de las importancias en regresión: qué mide la barra y en qué unidad. */
export function tituloEjeRegresion(kind: ExplanationKind, unidad: string | null): string {
  const en = unidad ? ` (${unidad})` : "";
  return kind === "global_permutation" ? `Aumento del RMSE${en}` : `Importancia${en}`;
}

/** Valor predicho de una explicación local (`prediction_value`), o `null` si no lo trae. */
export function valorPredicho(resultado: JsonObject | null): number | null {
  const v = resultado?.prediction_value;
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Tooltip de las barras con la unidad: importancia sin signo o contribución con signo. */
export function crearTooltipRegresion(
  unidad: string | null,
  local: boolean,
): ComponentType<{ active?: boolean; payload?: { payload?: unknown }[] }> {
  return function TooltipRegresion({ active, payload }) {
    if (!active || !payload || payload.length === 0) return null;
    const fila = payload[0]?.payload as Fila | undefined;
    if (!fila) return null;
    return (
      <div className="rounded-md border border-border bg-popover p-2 text-xs text-popover-foreground shadow-md">
        <p className="font-semibold">{fila.feature}</p>
        <p>{local ? formatoContribucion(fila.valor, unidad) : formatoImportancia(fila.valor, unidad)}</p>
        {fila.rule ? <p className="text-muted-foreground">{fila.rule}</p> : null}
      </div>
    );
  };
}

/** Color de una contribución local: sin juicio, con la paleta de equidad (`--chart-3` sube, `--chart-2` baja). */
export const colorContribucion = (valor: number) => `var(${valor < 0 ? "--chart-2" : "--chart-3"})`;

interface Props {
  kind: ExplanationKind;
  unidad: string | null;
  /** `prediction_value` de la explicación local. */
  predicho: number | null;
}

/** Cómo se lee el gráfico: qué mide cada barra y en qué unidad. */
export function LecturaRegresion({ kind, unidad, predicho }: Props) {
  const en = unidad ? `, en ${unidad}` : "";
  return (
    <div className="flex flex-col gap-1 text-sm" data-testid="explicacion-regresion">
      {predicho !== null ? (
        <p className="font-medium" data-testid="valor-predicho">
          Valor predicho: {formatoImportancia(predicho, unidad)}
        </p>
      ) : null}
      <p className="text-xs text-muted-foreground">
        {kind === "global_permutation"
          ? `Aumento del RMSE al desordenar la variable${en}. Cuanto más sube el error, más usa el modelo esa variable.`
          : kind === "global_shap"
            ? `Contribución media de cada variable al valor predicho, sin signo${en}.`
            : `Lo que cada variable suma (verde) o resta (rojo) al valor predicho${en}.`}
      </p>
    </div>
  );
}
