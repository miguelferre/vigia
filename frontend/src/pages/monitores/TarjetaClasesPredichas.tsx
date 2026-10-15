/**
 * Cuerpo de la tarjeta «Clases predichas» del bloque «Distribuciones»:
 * `details.prediction` como dos categorías con la
 * forma B compartida. Sustituye a la tabla de `clases-predichas.tsx`
 * (borrado) en `/monitores/deriva`; `prediccion-datos.ts` sigue siendo la
 * única lectura de `details.prediction`.
 *
 * `dominio`: nombra las dos clases con `nombreClasePredicha`
 * («Derivar»/«No derivar» en un dominio de derivación) en vez del literal
 * fijo «Clase 0»/«Clase 1».
 *
 * Recuentos: con `n_base`/`n_actual` en `details.prediction`, se
 * pasan los recuentos reales por clase (tasa x tamaño de ventana, redondeado,
 * igual que en `DrillImpactoDispar.tsx`) y se activa `mostrarRecuentos`; sin
 * ellos (evaluación anterior al cambio de backend), se sigue enseñando solo
 * el reparto en tasa, como hasta ahora.
 */

import { HistogramaBaseLote, construirFilasHistograma, distribucionesIdenticas } from "@/components/vigia";
import { extraerPrediccion } from "./prediccion-datos";
import { nombreClasePredicha } from "./confianza-por-clase";
import type { Measurement, EvaluationDetail, JsonObject } from "@/api/types";
import { formatoNumero, formatoCorto } from "@/lib/metrics";
import { Skeleton } from "@/components/ui/skeleton";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { TarjetaClasesPredichasK } from "./TarjetaClasesPredichasK";

export interface TarjetaClasesPredichasProps {
  evaluacion: EvaluationDetail;
  favorableLabel: number | null;
  medida: Measurement | undefined;
  /** `Project.domain`, para nombrar las clases con `nombreClasePredicha`. */
  dominio?: string | null;
}

export function TarjetaClasesPredichas({ evaluacion, favorableLabel, medida, dominio }: TarjetaClasesPredichasProps) {
  // Multiclase dibuja `k` barras desde `details.prediction.por_clase`; binario, las dos de siempre.
  const { caps, clases, favorables } = useTipoTarea(evaluacion.project_id);
  if (!caps) return <Skeleton className="h-48 w-full" />;
  if (caps.confianza === "por_clase") {
    return <TarjetaClasesPredichasK evaluacion={evaluacion} medida={medida} clases={clases} favorables={favorables} />;
  }
  const details = (evaluacion.result?.details as JsonObject | undefined) ?? null;
  const prediccion = extraerPrediccion(details);

  if (!prediccion || prediccion.rate_base === null || prediccion.rate_cur === null) {
    return <p className="text-sm text-muted-foreground">Sin datos de predicciones en esta evaluación.</p>;
  }

  const tramos = [0, 1].map((clase) => nombreClasePredicha(dominio, clase as 0 | 1, favorableLabel));
  const conRecuentos = prediccion.n_base !== null && prediccion.n_actual !== null;
  const base = conRecuentos
    ? [Math.round(prediccion.n_base! * (1 - prediccion.rate_base)), Math.round(prediccion.n_base! * prediccion.rate_base)]
    : [1 - prediccion.rate_base, prediccion.rate_base];
  const actual = conRecuentos
    ? [Math.round(prediccion.n_actual! * (1 - prediccion.rate_cur)), Math.round(prediccion.n_actual! * prediccion.rate_cur)]
    : [1 - prediccion.rate_cur, prediccion.rate_cur];

  const signo = (n: number) => (n >= 0 ? "+" : "−");
  const baseCur1 = prediccion.rate_cur * 100;
  const baseBase1 = prediccion.rate_base * 100;
  const diffPp = baseCur1 - baseBase1;
  const filas = construirFilasHistograma(tramos, base, actual);
  const identicas = distribucionesIdenticas(filas);

  return (
    <div className="flex flex-col gap-2">
      <HistogramaBaseLote
        tramos={tramos}
        base={base}
        actual={actual}
        mostrarRecuentos={conRecuentos}
        alto={200}
      />
      {identicas ? (
        <p className="text-xs text-muted-foreground">
          Las dos distribuciones son idénticas: la línea base y el lote reparten los {filas.length} tramos por igual.
        </p>
      ) : null}
      <p className="text-xs text-muted-foreground">
        Deriva de las predicciones <span className="font-semibold">{formatoNumero(medida?.value ?? null, 3)}</span>
        {medida?.threshold_high != null ? ` (umbral ≤ ${formatoNumero(medida.threshold_high, 3)})` : ""}
        {" · "}
        {tramos[1]}: <span className="font-semibold">{formatoCorto(baseBase1, 1)} %</span>
        {" → "}
        <span className="font-semibold">{formatoCorto(baseCur1, 1)} %</span>
        {" ("}
        {signo(diffPp)}
        {formatoCorto(Math.abs(diffPp), 1)} pp)
      </p>
    </div>
  );
}

export default TarjetaClasesPredichas;
