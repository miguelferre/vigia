/**
 * Drill-down de deriva: ranking de características
 * por `score`. Fuente: `result.details.features` de una `EvaluationDetail`
 * de monitor `drift` (`core/drift.py`). La frecuencia de clases predichas
 * (`details.prediction`) se movió a `TarjetaClasesPredichas.tsx` sobre
 * `prediccion-datos.ts`: el bloque «Distribuciones»
 * de `/monitores/deriva` la enseña ahora en la forma B, y el ranking de aquí
 * solo lo usa el onboarding (`RankingCaracteristicas` también es el export
 * por defecto).
 *
 * `details.confidence` no se pinta aquí (se muestra en su propia tarjeta): trae
 * `ks_stat`, `ks_p`, `psi`, `jensen_shannon_distance` y
 * `jensen_shannon_divergence` de la distribución de confianza de la
 * predicción, mismo tipo de estadístico que el ranking de características
 * pero a nivel global en vez de por característica. Podría ser una tercera
 * tarjeta ("confianza de la predicción") si hace falta.
 *
 * Las claves `ks_stat`/`ks_p`/`psi` (numéricas) y `chi2`/`p`/`js`
 * (categóricas) no son `metric_key` del motor y no tienen entrada en
 * `content/metricas-ayuda.json`: son estadísticos internos por
 * característica, así que su ayuda vive en `deriva-estadisticos.tsx` y no en
 * el ⓘ de la tarjeta.
 */

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { RankingBarras, type TooltipRankingProps } from "@/components/vigia";
import { useGuionDemo } from "@/api/queries-contenido";
import type { EvaluationDetail, JsonObject } from "@/api/types";
import { formatoNumero } from "@/lib/metrics";

import {
  AYUDA_ESTADISTICO,
  CabeceraEstadistico,
  extraerCaracteristicas,
  type FilaCaracteristica,
} from "./deriva-estadisticos";

/**
 * Un dataset clínico trae decenas de características (el de reumatología, más
 * de cincuenta): sin tope, el "ranking" es una lista completa donde la cola de
 * ceros entierra lo que importa y el bloque siguiente. Se enseñan las más
 * derivadas y el resto queda a un clic, como un paginado.
 */
const TOPE_CARACTERISTICAS = 10;

/* ---------- bloque A: ranking de características ---------- */

function TooltipCaracteristica({ active, payload }: TooltipRankingProps) {
  if (!active || !payload || payload.length === 0) return null;
  const fila = payload[0]?.payload as FilaCaracteristica | undefined;
  if (!fila) return null;
  return (
    <div className="rounded-md border border-border bg-popover p-2 text-xs text-popover-foreground shadow-md">
      <p className="font-semibold">{fila.featureLabel}</p>
      {fila.featureLabel !== fila.feature ? <p className="text-muted-foreground">{fila.feature}</p> : null}
      <p>Puntuación de deriva: {formatoNumero(fila.score)}</p>
      {fila.kind === "numerica" ? (
        <>
          <p>KS: {formatoNumero(fila.ks_stat)} (p {formatoNumero(fila.ks_p)})</p>
          <p>PSI: {formatoNumero(fila.psi)}</p>
        </>
      ) : fila.kind === "categorica" ? (
        <>
          <p>Chi cuadrado: {formatoNumero(fila.chi2)} (p {formatoNumero(fila.p)})</p>
          <p>JS: {formatoNumero(fila.js)}</p>
        </>
      ) : null}
    </div>
  );
}

export interface RankingCaracteristicasProps {
  evaluacion: EvaluationDetail;
}

export function RankingCaracteristicas({ evaluacion }: RankingCaracteristicasProps) {
  const details = (evaluacion.result?.details as JsonObject | undefined) ?? null;
  // `staleTime: Infinity`: mientras la petición no vuelva, `dominio` es
  // `undefined` y `extraerCaracteristicas` deja los nombres tal cual (no
  // bloquea el render).
  const dominio = useGuionDemo().data?.dominio;
  const todas = extraerCaracteristicas(details, dominio);
  const [verTodas, setVerTodas] = useState(false);
  const filas = verTodas ? todas : todas.slice(0, TOPE_CARACTERISTICAS);

  if (todas.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin características en el resultado de esta evaluación.</p>;
  }

  // Sin deriva en ninguna característica (el caso normal de una evaluación de
  // baseline contra sí misma) el gráfico saldría vacío con un eje inventado de
  // 0 a 4, que se lee como avería. Se dice con palabras y se deja la tabla.
  const sinDeriva = todas.every((f) => f.score === 0);

  return (
    <div className="flex flex-col gap-4">
      {sinDeriva ? (
        <p className="text-sm text-muted-foreground">
          Ninguna de las {todas.length} características se ha movido respecto a la línea base:
          todas puntúan 0.
        </p>
      ) : (
        <RankingBarras
          datos={filas}
          claveCategoria="featureLabel"
          claveValor="score"
          color={() => "var(--chart-2)"}
          tooltip={TooltipCaracteristica}
          clave={(f) => f.feature}
        />
      )}
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Característica</TableHead>
              <TableHead>Tipo</TableHead>
              <TableHead>
                <CabeceraEstadistico {...AYUDA_ESTADISTICO.ks} />
              </TableHead>
              <TableHead>
                <CabeceraEstadistico {...AYUDA_ESTADISTICO.psi} />
              </TableHead>
              <TableHead>
                <CabeceraEstadistico {...AYUDA_ESTADISTICO.chi2} />
              </TableHead>
              <TableHead>
                <CabeceraEstadistico {...AYUDA_ESTADISTICO.js} />
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.map((fila) => (
              <TableRow key={fila.feature}>
                <TableCell className="max-w-64 truncate" title={fila.feature}>
                  {fila.featureLabel}
                </TableCell>
                <TableCell>{fila.kind === "numerica" ? "Numérica" : fila.kind === "categorica" ? "Categórica" : "—"}</TableCell>
                <TableCell className="tabular-nums">
                  {fila.kind === "numerica" ? `${formatoNumero(fila.ks_stat)} (p ${formatoNumero(fila.ks_p)})` : "—"}
                </TableCell>
                <TableCell className="tabular-nums">{fila.kind === "numerica" ? formatoNumero(fila.psi) : "—"}</TableCell>
                <TableCell className="tabular-nums">
                  {fila.kind === "categorica" ? `${formatoNumero(fila.chi2)} (p ${formatoNumero(fila.p)})` : "—"}
                </TableCell>
                <TableCell className="tabular-nums">{fila.kind === "categorica" ? formatoNumero(fila.js) : "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {todas.length > TOPE_CARACTERISTICAS ? (
        <div className="flex items-center gap-3">
          <Button size="sm" variant="outline" onClick={() => setVerTodas((v) => !v)}>
            {verTodas ? `Ver solo las ${TOPE_CARACTERISTICAS} primeras` : `Ver las ${todas.length} características`}
          </Button>
          <span className="text-xs text-muted-foreground">
            {verTodas ? `${todas.length} de ${todas.length}` : `${TOPE_CARACTERISTICAS} de ${todas.length}, por deriva descendente`}
          </span>
        </div>
      ) : null}
    </div>
  );
}

export default RankingCaracteristicas;
