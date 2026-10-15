/**
 * Tabla por clase de la calidad multiclase (`details.por_clase`):
 * precisión, sensibilidad (recall), F1 y soporte de cada clase contra el resto,
 * más cuántas veces la predijo el modelo. Es una tabla informativa: ninguna
 * celda tiene umbral ni estado, y por eso no abre alertas.
 *
 * Una clase con menos filas que el mínimo por grupo en la ventana no
 * tiene métricas por clase: se escribe «sin datos» con su motivo, nunca 0.
 */

import { cn } from "@/lib/utils";
import { formatoNumero } from "@/lib/metrics";

import type { FilaPorClase } from "./calidad-multiclase-datos";

function celda(v: number | null, insuficiente: boolean) {
  if (insuficiente || v === null) return <span className="text-muted-foreground">sin datos</span>;
  return formatoNumero(v);
}

export interface TablaPorClaseProps {
  filas: FilaPorClase[];
  f1Ponderada?: number | null;
  /** Clases del proyecto en su orden; las filas se ordenan igual. */
  orden?: string[];
  className?: string;
}

export function TablaPorClase({ filas, f1Ponderada, orden, className }: TablaPorClaseProps) {
  if (filas.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin tabla por clase en esta evaluación.</p>;
  }
  const idx = (c: string) => {
    const i = orden?.indexOf(c) ?? -1;
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  const ordenadas = orden ? [...filas].sort((a, b) => idx(a.clase) - idx(b.clase)) : filas;
  const hayInsuficientes = ordenadas.some((f) => f.insuficiente);
  const th = "sticky top-0 z-10 border-b bg-card px-3 py-2 text-right font-medium text-muted-foreground";

  return (
    <div className={cn("flex min-w-0 flex-col gap-2", className)} data-testid="tabla-por-clase">
      <p className="text-xs text-muted-foreground">
        Cada clase contra el resto, en la ventana de la última evaluación. Es una tabla informativa: no tiene
        umbral y no abre alertas.
      </p>
      <div
        role="region"
        tabIndex={0}
        aria-label="Calidad por clase"
        className="max-h-96 max-w-full overflow-auto rounded-lg border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <table className="w-max min-w-full border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th className={cn(th, "left-0 z-20 text-left")}>Clase</th>
              <th className={th}>Precisión</th>
              <th className={th}>Sensibilidad</th>
              <th className={th}>F1</th>
              <th className={th}>Casos reales</th>
              <th className={th}>Predichas</th>
            </tr>
          </thead>
          <tbody>
            {ordenadas.map((f) => (
              <tr key={f.clase}>
                <th
                  scope="row"
                  title={f.clase}
                  className="sticky left-0 border-b bg-card px-3 py-2 text-left font-normal max-w-44 sm:max-w-72 whitespace-normal [overflow-wrap:anywhere]"
                >
                  {f.clase}
                </th>
                <td className="border-b px-3 py-2 text-right tabular-nums">{celda(f.precision, f.insuficiente)}</td>
                <td className="border-b px-3 py-2 text-right tabular-nums">{celda(f.recall, f.insuficiente)}</td>
                <td className="border-b px-3 py-2 text-right tabular-nums">{celda(f.f1, f.insuficiente)}</td>
                <td className="border-b px-3 py-2 text-right tabular-nums">
                  {f.soporte === null ? "n/d" : f.soporte.toLocaleString("es-ES")}
                </td>
                <td className="border-b px-3 py-2 text-right tabular-nums">
                  {f.predichas === null ? "n/d" : f.predichas.toLocaleString("es-ES")}
                  {f.tasaPredicha !== null ? (
                    <span className="text-xs text-muted-foreground">
                      {" "}
                      ({(f.tasaPredicha * 100).toLocaleString("es-ES", { maximumFractionDigits: 1 })} %)
                    </span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hayInsuficientes ? (
        <p className="text-xs text-muted-foreground">
          «Sin datos»: la clase tiene menos casos reales en la ventana que el mínimo por grupo. No se calcula, para no
          dar un valor de una muestra demasiado pequeña.
        </p>
      ) : null}
      {f1Ponderada !== null && f1Ponderada !== undefined ? (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer hover:text-foreground">Otra forma de promediar la F1</summary>
          <p className="mt-1">
            F1 ponderada por el tamaño de cada clase:{" "}
            <span className="font-semibold text-foreground tabular-nums">{formatoNumero(f1Ponderada)}</span>. El titular
            de la pantalla es la F1 macro, que da el mismo peso a todas las clases.
          </p>
        </details>
      ) : null}
    </div>
  );
}

export default TablaPorClase;
