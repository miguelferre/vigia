/**
 * Cuerpo de la tarjeta «Clases predichas» en multiclase:
 * `details.prediction.por_clase` como `k` barras (una por clase predicha) con
 * la forma B compartida, línea base frente a lote. `TarjetaClasesPredichas.tsx`
 * elige esta rama por `caps.confianza === "por_clase"`; la binaria sigue allí,
 * sin cambios.
 *
 * Con más de `MAX_BARRAS` clases se dibujan las que más pesan (en la línea
 * base o en el lote) y el resto se agrupa en «Otras N clases»; la tabla
 * plegada de debajo lleva todas, con el cambio de cada una. El texto nombra la
 * clase con el mayor cambio de reparto, que es lo que mueve la puntuación de
 * deriva (distancia de Jensen-Shannon entre los repartos por clase).
 */

import { HistogramaBaseLote, construirFilasHistograma, distribucionesIdenticas } from "@/components/vigia";
import type { EvaluationDetail, JsonObject, Measurement } from "@/api/types";
import { formatoCorto, formatoNumero } from "@/lib/metrics";

import { extraerPrediccion, type FilaPrediccionClase } from "./prediccion-datos";

/** Con más clases que esto, el gráfico enseña las que más pesan y agrupa el resto. */
const MAX_BARRAS = 8;

export interface TarjetaClasesPredichasKProps {
  evaluacion: EvaluationDetail;
  medida: Measurement | undefined;
  /** Clases del proyecto en su orden (`useTipoTarea().clases`); sin ellas, el orden de `details`. */
  clases: string[];
  /** Conjunto favorable del proyecto (claves): se marca en la tabla. */
  favorables: string[];
}

function pp(v: number | null): string {
  if (v === null) return "n/d";
  const signo = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${signo}${formatoCorto(Math.abs(v) * 100, 1)} pp`;
}

function porcentaje(v: number | null): string {
  return v === null ? "n/d" : `${formatoCorto(v * 100, 1)} %`;
}

export function TarjetaClasesPredichasK({ evaluacion, medida, clases, favorables }: TarjetaClasesPredichasKProps) {
  const details = (evaluacion.result?.details as JsonObject | undefined) ?? null;
  const prediccion = extraerPrediccion(details);
  const filasDetalle = prediccion?.porClase ?? null;
  if (!prediccion || !filasDetalle) {
    return <p className="text-sm text-muted-foreground">Sin datos de predicciones en esta evaluación.</p>;
  }

  // Orden del proyecto; las clases que el proyecto no declare, al final.
  const pos = (c: string) => {
    const i = clases.indexOf(c);
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  const filas: FilaPrediccionClase[] = [...filasDetalle].sort((a, b) => pos(a.clase) - pos(b.clase));
  const k = filas.length;
  const conRecuentos = prediccion.n_base !== null && prediccion.n_actual !== null;
  const aPeso = (tasa: number | null, n: number | null): number =>
    conRecuentos && n !== null ? Math.round((tasa ?? 0) * n) : (tasa ?? 0);
  const peso = (f: FilaPrediccionClase) => ({
    base: aPeso(f.base, prediccion.n_base),
    actual: aPeso(f.actual, prediccion.n_actual),
  });

  // Gráfico: todas si caben; si no, las que más pesan y «Otras».
  let dibujadas = filas;
  let otras: FilaPrediccionClase[] = [];
  if (k > MAX_BARRAS) {
    const porPeso = [...filas].sort((a, b) => Math.max(b.base ?? 0, b.actual ?? 0) - Math.max(a.base ?? 0, a.actual ?? 0));
    // La clase con el mayor cambio se dibuja siempre, pese lo que pese.
    const forzada = prediccion.claseMayorCambio;
    const base0 = porPeso.filter((f) => f.clase !== forzada).slice(0, forzada ? MAX_BARRAS - 2 : MAX_BARRAS - 1);
    const tope = new Set([...base0.map((f) => f.clase), ...(forzada && filas.some((f) => f.clase === forzada) ? [forzada] : [])]);
    dibujadas = filas.filter((f) => tope.has(f.clase));
    otras = filas.filter((f) => !tope.has(f.clase));
  }
  const tramos = dibujadas.map((f) => f.clase);
  const base = dibujadas.map((f) => peso(f).base);
  const actual = dibujadas.map((f) => peso(f).actual);
  if (otras.length > 0) {
    tramos.push(`Otras ${otras.length} clases`);
    base.push(otras.reduce((a, f) => a + peso(f).base, 0));
    actual.push(otras.reduce((a, f) => a + peso(f).actual, 0));
  }
  const filasHist = construirFilasHistograma(tramos, base, actual);
  const identicas = distribucionesIdenticas(filasHist);
  const mayor = prediccion.claseMayorCambio ? filas.find((f) => f.clase === prediccion.claseMayorCambio) : undefined;

  return (
    <div className="flex flex-col gap-2" data-testid="clases-predichas-k">
      <HistogramaBaseLote
        tramos={tramos}
        base={base}
        actual={actual}
        mostrarRecuentos={conRecuentos}
        alto={otras.length > 0 || k > 4 ? 240 : 200}
        etiquetasLargas
      />
      {identicas ? (
        <p className="text-xs text-muted-foreground">
          Las dos distribuciones son idénticas: la línea base y el lote reparten las {k} clases por igual.
        </p>
      ) : null}
      <p className="text-xs text-muted-foreground">
        Deriva de las predicciones <span className="font-semibold">{formatoNumero(medida?.value ?? null, 3)}</span>
        {medida?.threshold_high != null ? ` (umbral ≤ ${formatoNumero(medida.threshold_high, 3)})` : ""}
        {mayor ? (
          <>
            {" · "}La clase que más cambia: <span className="font-semibold">{mayor.clase}</span>,{" "}
            <span className="font-semibold">{porcentaje(mayor.base)}</span>
            {" → "}
            <span className="font-semibold">{porcentaje(mayor.actual)}</span> ({pp(prediccion.cambioMayor ?? mayor.diff)})
          </>
        ) : null}
        {prediccion.rate_base !== null && prediccion.rate_cur !== null && favorables.length > 0 ? (
          <>
            {" · "}Clases favorables ({favorables.join(", ")}):{" "}
            <span className="font-semibold">{porcentaje(prediccion.rate_base)}</span>
            {" → "}
            <span className="font-semibold">{porcentaje(prediccion.rate_cur)}</span>
          </>
        ) : null}
      </p>
      {k > MAX_BARRAS ? (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Ver las {k} clases</summary>
          <div className="mt-2 max-h-72 overflow-auto rounded-lg border">
            <table className="w-max min-w-full border-separate border-spacing-0 text-xs">
              <thead>
                <tr>
                  {["Clase", "Línea base", "Lote", "Cambio"].map((t, i) => (
                    <th
                      key={t}
                      className={`sticky top-0 border-b bg-card px-3 py-1.5 font-medium text-muted-foreground ${i === 0 ? "left-0 z-10 text-left" : "text-right"}`}
                    >
                      {t}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filas.map((f) => (
                  <tr key={f.clase}>
                    <th
                      scope="row"
                      className="sticky left-0 max-w-56 whitespace-normal border-b bg-card px-3 py-1.5 text-left font-normal [overflow-wrap:anywhere]"
                    >
                      {f.clase}
                      {favorables.includes(f.clase) ? <span className="text-muted-foreground"> (favorable)</span> : null}
                    </th>
                    <td className="border-b px-3 py-1.5 text-right tabular-nums">{porcentaje(f.base)}</td>
                    <td className="border-b px-3 py-1.5 text-right tabular-nums">{porcentaje(f.actual)}</td>
                    <td className="border-b px-3 py-1.5 text-right tabular-nums">{pp(f.diff)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </div>
  );
}

export default TarjetaClasesPredichasK;
