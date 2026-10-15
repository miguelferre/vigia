/**
 * Matriz de confusión `k x k` de una evaluación de calidad multiclase. Filas: la clase real. Columnas: la clase que predijo el modelo
 * (`details.confusion_matrix`, mismo orden que `classes`). Es la orientación
 * del backend y la habitual en multiclase; la 2x2 binaria de
 * `MatrizConfusion.tsx` conserva la suya.
 *
 * Legible con nombres largos y hasta 20 clases sin desbordar la página:
 *
 * - La tabla vive en un contenedor con desplazamiento propio (vertical y
 *   horizontal), con la cabecera y la columna de clases fijas.
 * - Hasta 8 clases, las columnas llevan el nombre de la clase (en varias
 *   líneas) y cada celda el porcentaje de su fila. Con más, las columnas llevan
 *   el número de la clase, que repite la columna de la izquierda («3 ·
 *   Nombre»), y la celda solo el recuento.
 * - Color: diagonal (acierta) en verde, fuera de la diagonal (confunde) en rojo,
 *   con intensidad según la proporción de la fila. El número va siempre, el
 *   color no es la única señal: la diagonal lleva además trazo grueso.
 */

import { cn } from "@/lib/utils";

import type { MatrizK } from "./calidad-multiclase-datos";

/** Hasta este número de clases, las columnas llevan el nombre; con más, el número. */
const MAX_CLASES_CON_NOMBRE = 8;

function pct(parte: number, total: number): string {
  if (total === 0) return "0 %";
  return `${((parte / total) * 100).toLocaleString("es-ES", { maximumFractionDigits: 0 })} %`;
}

function fondoCelda(valor: number, totalFila: number, diagonal: boolean): string | undefined {
  if (valor === 0 || totalFila === 0) return undefined;
  const parte = valor / totalFila;
  if (diagonal) return `color-mix(in srgb, var(--state-ok) ${Math.round(10 + 50 * parte)}%, transparent)`;
  return `color-mix(in srgb, var(--state-alert) ${Math.round(Math.min(55, 12 + parte * 160))}%, transparent)`;
}

export interface MatrizConfusionKProps {
  matriz: MatrizK;
  className?: string;
}

export function MatrizConfusionK({ matriz, className }: MatrizConfusionKProps) {
  const { clases, matriz: m } = matriz;
  const k = clases.length;
  const conNombre = k <= MAX_CLASES_CON_NOMBRE;
  const totalFila = m.map((fila) => fila.reduce((a, b) => a + b, 0));
  const totalCol = clases.map((_, j) => m.reduce((a, fila) => a + (fila[j] ?? 0), 0));
  const total = totalFila.reduce((a, b) => a + b, 0);
  const aciertos = m.reduce((a, fila, i) => a + (fila[i] ?? 0), 0);
  const nombre = (i: number) => clases[i] ?? "";

  const cabecera = "sticky top-0 z-10 border-b bg-card px-2 py-1.5 align-bottom font-medium text-muted-foreground";
  const laterales =
    "sticky left-0 z-10 border-r bg-card px-2 py-1.5 text-left font-medium max-w-40 sm:max-w-64 whitespace-normal [overflow-wrap:anywhere]";

  return (
    <div className={cn("flex min-w-0 flex-col gap-2", className)} data-testid="matriz-confusion-k">
      <p className="text-xs text-muted-foreground">
        Filas: la clase real. Columnas: la clase que predijo el modelo. La diagonal son los aciertos
        ({aciertos.toLocaleString("es-ES")} de {total.toLocaleString("es-ES")} casos); fuera de la diagonal, el
        modelo confunde una clase con otra.
        {conNombre ? " Cada casilla lleva su porcentaje sobre la fila." : " Las columnas llevan el número de la clase; el nombre está en la fila."}
      </p>
      {/* `tabIndex` y `role`: un contenedor con desplazamiento tiene que poder recorrerse con el teclado. */}
      <div
        role="region"
        tabIndex={0}
        aria-label={`Matriz de confusión de ${k} clases, clase real en filas y clase predicha en columnas`}
        className="max-h-[34rem] max-w-full overflow-auto rounded-lg border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <table className="w-max min-w-full border-separate border-spacing-0 text-xs">
          <thead>
            <tr>
              <th className={cn(cabecera, "left-0 z-20 border-r text-left")}>Real ↓ · Predicho →</th>
              {clases.map((c, j) => (
                <th
                  key={c}
                  scope="col"
                  title={c}
                  className={cn(cabecera, "text-center", conNombre ? "min-w-20 max-w-28 whitespace-normal [overflow-wrap:anywhere]" : "min-w-10")}
                >
                  {conNombre ? c : j + 1}
                </th>
              ))}
              <th scope="col" className={cn(cabecera, "text-center")}>
                Casos reales
              </th>
            </tr>
          </thead>
          <tbody>
            {m.map((fila, i) => (
              <tr key={clases[i]}>
                <th scope="row" title={nombre(i)} className={cn(laterales, "border-b")}>
                  {conNombre ? nombre(i) : `${i + 1} · ${nombre(i)}`}
                </th>
                {fila.map((valor, j) => (
                  <td
                    key={clases[j]}
                    title={`Real: ${nombre(i)} · Predicho: ${nombre(j)} · ${valor.toLocaleString("es-ES")} casos (${pct(valor, totalFila[i] ?? 0)} de la fila)`}
                    className={cn(
                      "border-b border-l px-1.5 py-1.5 text-center tabular-nums",
                      i === j && "font-semibold shadow-[inset_0_0_0_2px_var(--state-ok)]",
                      valor === 0 && "text-muted-foreground",
                    )}
                    style={{ backgroundColor: fondoCelda(valor, totalFila[i] ?? 0, i === j) }}
                  >
                    <span className="block">{valor.toLocaleString("es-ES")}</span>
                    {conNombre ? (
                      <span className="block text-[10px] font-normal text-muted-foreground">{pct(valor, totalFila[i] ?? 0)}</span>
                    ) : null}
                  </td>
                ))}
                <td className="border-b border-l px-2 py-1.5 text-center font-medium tabular-nums">
                  {(totalFila[i] ?? 0).toLocaleString("es-ES")}
                </td>
              </tr>
            ))}
            <tr>
              <th scope="row" className={cn(laterales, "border-b-0")}>
                Predichas
              </th>
              {totalCol.map((v, j) => (
                <td key={clases[j]} className="border-l px-1.5 py-1.5 text-center font-medium tabular-nums">
                  {v.toLocaleString("es-ES")}
                </td>
              ))}
              <td className="border-l px-2 py-1.5 text-center font-semibold tabular-nums">{total.toLocaleString("es-ES")}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default MatrizConfusionK;
