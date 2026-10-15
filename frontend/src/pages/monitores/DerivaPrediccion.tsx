/**
 * «Distribución de la predicción» de `/monitores/deriva` en regresión: sustituye a las tarjetas de confianza y de clases predichas, que no
 * existen cuando el modelo da un número. Histograma de la predicción de la
 * línea base frente al lote (`HistogramaBaseLote`, mismos cortes), con KS y
 * PSI (o el motivo si no hay PSI) y la diferencia de medias en la unidad, con
 * signo y dicha con palabras. Si los dos lados tienen valor real, una línea
 * aparte con la deriva del valor real, que no tiene umbral.
 */

import {
  HistogramaBaseLote,
  construirFilasHistograma,
  etiquetasDeBordes,
  fraseTramosQueMasCambian,
} from "@/components/vigia";
import type { AyudaMetrica } from "@/api/queries-contenido";
import type { EvaluationDetail } from "@/api/types";
import { medida } from "@/components/vigia/calculo-datos";
import { formatoMetrica, formatoNumero } from "@/lib/metrics";

import { TarjetaDistribucion } from "./TarjetaDistribucion";
import { AYUDA_ESTADISTICO, CabeceraEstadistico } from "./deriva-estadisticos";
import { fraseDiferenciaMedias, leerEtiquetaDeriva, leerPrediccionDeriva } from "./regresion-datos";

/** Tarjeta de «Distribución de la predicción» (sustituye a confianza y clases predichas en regresión). */
export function TarjetaPrediccion({
  evaluacion,
  unidad,
  numeroLote,
  ayuda,
}: {
  evaluacion: EvaluationDetail;
  unidad: string | null;
  numeroLote: string;
  ayuda: AyudaMetrica | undefined;
}) {
  return (
    <TarjetaDistribucion
      titulo="Distribución de la predicción"
      subtitulo={`Valor que predice el modelo, línea base frente a lote ${numeroLote}`}
      metricKey="prediction_drift_score"
      estado={medida(evaluacion, "prediction_drift_score")?.state}
      ayuda={ayuda}
    >
      <DerivaPrediccion result={evaluacion.result} unidad={unidad} numeroLote={numeroLote} />
    </TarjetaDistribucion>
  );
}

function DerivaPrediccion({ result, unidad, numeroLote }: { result: unknown; unidad: string | null; numeroLote: string }) {
  const p = leerPrediccionDeriva(result);
  if (!p) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="sin-prediccion-deriva">
        Sin datos de la predicción en esta evaluación: hace falta una línea base con predicciones y un lote evaluado.
      </p>
    );
  }
  const etiqueta = leerEtiquetaDeriva(result);
  const tramos = etiquetasDeBordes(p.binEdges);
  const frase = fraseTramosQueMasCambian(construirFilasHistograma(tramos, p.base, p.actual), 3);
  const nBase = p.base.reduce((a, b) => a + b, 0);
  const nActual = p.actual.reduce((a, b) => a + b, 0);
  return (
    <div className="flex flex-col gap-3" data-testid="deriva-prediccion">
      <HistogramaBaseLote
        tramos={tramos}
        base={p.base}
        actual={p.actual}
        prefijoTramo="Predicción"
        alto={230}
        tituloEjeX={`Predicción del modelo${unidad ? ` (${unidad})` : ""}, línea base frente a lote ${numeroLote}`}
      />
      <div className="flex flex-wrap items-center gap-3.5 text-xs text-muted-foreground tabular-nums">
        <span>
          n base <b className="font-semibold text-foreground">{formatoNumero(nBase, 0)}</b>
        </span>
        <span>
          n lote <b className="font-semibold text-foreground">{formatoNumero(nActual, 0)}</b>
        </span>
        <span className="inline-flex items-center gap-1">
          <CabeceraEstadistico {...AYUDA_ESTADISTICO.ks} />
          <b className="font-semibold text-foreground">{formatoNumero(p.ks, 3)}</b>
          {p.ksP !== null ? <> (p {formatoNumero(p.ksP, 3)})</> : null}
        </span>
        <span className="inline-flex items-center gap-1" data-testid="deriva-psi">
          <CabeceraEstadistico {...AYUDA_ESTADISTICO.psi} />
          {p.psi !== null ? (
            <b className="font-semibold text-foreground">{formatoNumero(p.psi, 2)}</b>
          ) : (
            <span>no calculado: {p.psiMotivo ?? "la predicción tiene pocos valores distintos"}</span>
          )}
        </span>
      </div>
      <p className="text-xs text-muted-foreground" data-testid="deriva-diferencia-medias">
        Media de la predicción: {formatoMetrica("mean_absolute_error", p.mediaBase, unidad)} en la línea base y{" "}
        {formatoMetrica("mean_absolute_error", p.mediaActual, unidad)} en el lote (diferencia{" "}
        <b className="font-semibold text-foreground">{formatoMetrica("diferencia_medias", p.diferenciaMedias, unidad)}</b>).{" "}
        {fraseDiferenciaMedias(p.diferenciaMedias, unidad)}
      </p>
      {frase ? <p className="text-xs text-muted-foreground">{frase}</p> : null}
      {etiqueta ? (
        <p className="text-xs text-muted-foreground" data-testid="deriva-etiqueta">
          Valor real, sin umbral: KS {formatoNumero(etiqueta.ks, 3)}, diferencia de medias{" "}
          {formatoMetrica("diferencia_medias", etiqueta.diferenciaMedias, unidad)}.
        </p>
      ) : null}
    </div>
  );
}
