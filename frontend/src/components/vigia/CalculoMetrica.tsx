/**
 * «Cómo se ha calculado», por métrica ampliada: decide qué bloque enseñar a partir de `metric_key`, no de
 * `monitor_type` como hacía `calculo.tsx` antes. `distribucionesEnPantalla`:
 * en `/monitores/deriva` la confianza y las variables ya están
 * en el bloque «Distribuciones», así que aquí se enlaza en vez de repetirlas.
 *
 * el párrafo de arriba del bloque es `textoQueMide` (una frase) en
 * todos los caminos, impacto dispar incluido; el resto de la presentación
 * (fórmula, resultado, umbral, estado) es `CajaFormula`, vía
 * `FormulaInstanciada` o (impacto dispar) `EscalaCociente`. Vale también
 * fuera del bloque «Distribuciones» (panel de alerta, `/alertas/:id`):
 * `confidence_drift_score` y `feature_drift_score` tienen `formula` en
 * `metricas-ayuda.json`, así que la caja va antepuesta a su histograma o
 * lista de variables en vez de sustituirla.
 */

import type { AyudaMetrica, ContenidoMetricas } from "@/api/queries-contenido";
import type { EvaluationDetail } from "@/api/types";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { ayudaPorTipo } from "@/lib/tipo-tarea";

import { textoQueMide } from "./AyudaTexto";
import { ColumnasCalculo, FormulaInstanciada } from "./CalculoFormula";
import { esReglaCruzada, medida } from "./calculo-datos";
import { DrillImpactoDispar } from "./DrillImpactoDispar";
import { DrillTasasError } from "./DrillTasasError";
import { DerivaVariables } from "@/pages/monitores/deriva-variables";
import { HistogramaConfianza } from "@/pages/monitores/histograma-confianza";
import { MatrizConfusion } from "./MatrizConfusion";
import { leerDetalleCalidadMulticlase } from "./calidad-multiclase-datos";
import { TablaPorClase } from "./TablaPorClase";

/** Impacto dispar: conserva su drill actual, ya bien resuelto. */
const IMPACTO_DISPAR = new Set(["fairness_value", "disparate_impact"]);

/** Equidad, diferencias de tasa de error por grupo: fórmula + tabla de tasas con esas filas resaltadas. */
const FILAS_TASAS: Record<string, string[]> = {
  false_negative_rate_difference: ["fnr"],
  false_positive_rate_difference: ["fpr"],
  average_odds_difference: ["fpr", "tpr"],
  average_abs_odds_difference: ["fpr", "tpr"],
};

/** Calidad, derivadas de la matriz de confusión: fórmula + matriz con esas celdas resaltadas. */
const CELDAS_MATRIZ: Record<string, Array<"tp" | "fp" | "fn" | "tn">> = {
  accuracy: ["tp", "tn", "fp", "fn"],
  precision: ["tp", "fp"],
  recall: ["tp", "fn"],
  true_positive_rate: ["tp", "fn"],
  false_positive_rate: ["fp", "tn"],
  matthews_correlation_coefficient: ["tp", "tn", "fp", "fn"],
  f1_measure: ["tp", "fp", "fn"],
};

/**
 * Multiclase: la matriz `k x k` explica la exactitud y MCC (la diagonal frente al
 * total); la tabla por clase explica el promedio macro de precisión, sensibilidad y F1. Las demás
 * (`false_positive_rate`, etc.) se quedan con la fórmula sola: no hay una tabla que las instancie.
 */
const MATRIZ_K = new Set(["accuracy", "matthews_correlation_coefficient", "false_positive_rate"]);
const TABLA_POR_CLASE = new Set(["precision", "recall", "true_positive_rate", "f1_measure"]);

function PorClaseDeEvaluacion({ evaluacion }: { evaluacion: EvaluationDetail }) {
  const { clases } = useTipoTarea(evaluacion.project_id);
  const d = leerDetalleCalidadMulticlase(evaluacion.result);
  return <TablaPorClase filas={d.porClase} f1Ponderada={d.f1Ponderada} orden={clases} />;
}

/** Deriva sin cálculo reproducible en Vigía: solo el motivo de la medida. */
const DERIVA_SIN_DATOS = new Set([
  "input_metadata_drift_score",
  "output_metadata_drift_score",
  "model_quality_score",
]);

export interface CalculoMetricaProps {
  metricKey: string;
  ayuda: AyudaMetrica | undefined;
  evaluacion: EvaluationDetail;
  todaAyuda: ContenidoMetricas | undefined;
  /** Omite el párrafo de definición cuando la pantalla ya lo enseña (AL2). */
  sinDefinicion?: boolean;
  /** `/monitores/deriva`: confianza y variables ya están en el bloque «Distribuciones». */
  distribucionesEnPantalla?: boolean;
}

/** Métricas cuya distribución vive en el bloque «Distribuciones» cuando está en pantalla. */
const EN_BLOQUE_DISTRIBUCIONES = new Set(["confidence_drift_score", "feature_drift_score"]);

/** Camino de solo texto de una regla cruzada: cómo se calcula y cómo se lee, sin resultado ni evaluación. */
export function CalculoCruzada({ ayuda, sinDefinicion }: { ayuda: AyudaMetrica | undefined; sinDefinicion?: boolean }) {
  if (!ayuda) {
    return <p className="text-sm text-muted-foreground">Cargando la ayuda de esta regla…</p>;
  }
  return (
    <div className="flex flex-col gap-3" data-testid="calculo-cruzada">
      {sinDefinicion ? null : <p className="text-sm text-muted-foreground">{ayuda.que_mide}</p>}
      {ayuda.formula ? (
        <p className="text-sm">
          <span className="font-semibold">Cómo se calcula. </span>
          {ayuda.formula}
        </p>
      ) : null}
      <p className="text-sm text-muted-foreground">
        <span className="font-semibold">Cómo se lee. </span>
        {ayuda.como_se_lee}
      </p>
    </div>
  );
}

export function CalculoMetrica({
  metricKey,
  ayuda,
  evaluacion,
  todaAyuda,
  sinDefinicion,
  distribucionesEnPantalla,
}: CalculoMetricaProps) {
  const { tipo, caps } = useTipoTarea(evaluacion.project_id);
  // idempotente; protege a quien pase la ayuda cruda (`AlertaPanel`).
  ayuda = ayuda ? ayudaPorTipo(ayuda, tipo) : ayuda;
  if (esReglaCruzada(metricKey, ayuda)) return <CalculoCruzada ayuda={ayuda} sinDefinicion={sinDefinicion} />;
  if (IMPACTO_DISPAR.has(metricKey)) {
    // el párrafo de arriba es `textoQueMide` en todos los caminos,
    // impacto dispar incluido (antes se saltaba directo al drill-down).
    return (
      <div className="flex flex-col gap-4">
        {sinDefinicion ? null : <p className="text-sm text-muted-foreground">{textoQueMide(ayuda)}</p>}
        <DrillImpactoDispar evaluacion={evaluacion} />
      </div>
    );
  }
  if (!distribucionesEnPantalla && EN_BLOQUE_DISTRIBUCIONES.has(metricKey) && ayuda) {
    // Fuera del bloque
    // «Distribuciones» (panel de alerta, `/alertas/:id`) estas dos métricas
    // también tienen `formula`, así que llevan la misma caja que el resto,
    // antepuesta a su histograma o lista de variables.
    return (
      <div className="flex flex-col gap-4">
        {sinDefinicion ? null : <p className="text-sm text-muted-foreground">{textoQueMide(ayuda)}</p>}
        <FormulaInstanciada metricKey={metricKey} ayuda={ayuda} evaluacion={evaluacion} todaAyuda={todaAyuda} />
        {metricKey === "feature_drift_score" ? (
          <DerivaVariables evaluacion={evaluacion} />
        ) : (
          <HistogramaConfianza evaluacion={evaluacion} />
        )}
      </div>
    );
  }
  // Sin `ayuda` todavía (consulta de contenido en curso): se conserva solo la
  // distribución, como antes, en vez de bloquear la pantalla.
  if (!distribucionesEnPantalla && metricKey === "feature_drift_score") {
    return <DerivaVariables evaluacion={evaluacion} />;
  }
  if (!distribucionesEnPantalla && metricKey === "confidence_drift_score") {
    return <HistogramaConfianza evaluacion={evaluacion} />;
  }
  if (distribucionesEnPantalla && EN_BLOQUE_DISTRIBUCIONES.has(metricKey) && ayuda) {
    return (
      <div className="flex flex-col gap-4">
        {sinDefinicion ? null : <p className="text-sm text-muted-foreground">{textoQueMide(ayuda)}</p>}
        <FormulaInstanciada metricKey={metricKey} ayuda={ayuda} evaluacion={evaluacion} todaAyuda={todaAyuda} />
        <p className="text-xs text-muted-foreground">
          La distribución de esta métrica está en el bloque{" "}
          <a href="#distribuciones" className="underline">
            Distribuciones
          </a>
          , encima de esta sección.
        </p>
      </div>
    );
  }
  if (DERIVA_SIN_DATOS.has(metricKey)) {
    const m = medida(evaluacion, metricKey);
    return (
      <p className="text-sm text-muted-foreground">
        {textoQueMide(ayuda, "Sin ayuda para esta métrica.")}
        {m?.motivo ? ` ${m.motivo}` : ""}
      </p>
    );
  }
  if (!ayuda) {
    return <p className="text-sm text-muted-foreground">Sin ayuda para esta métrica.</p>;
  }

  const filasTasas = FILAS_TASAS[metricKey];
  const celdasMatriz = CELDAS_MATRIZ[metricKey];
  const formula = <FormulaInstanciada metricKey={metricKey} ayuda={ayuda} evaluacion={evaluacion} todaAyuda={todaAyuda} />;
  // la fórmula manda, a la derecha de su tabla de apoyo (tasas de
  // error o matriz de confusión) desde `@lg`; sin tabla, se queda sola.
  if (caps?.matriz === "kxk" && (MATRIZ_K.has(metricKey) || TABLA_POR_CLASE.has(metricKey))) {
    // La matriz `k x k` y la tabla por clase necesitan todo el ancho: fórmula arriba, tabla debajo.
    return (
      <div className="flex flex-col gap-4">
        {sinDefinicion ? null : <p className="text-sm text-muted-foreground">{textoQueMide(ayuda)}</p>}
        {formula}
        {MATRIZ_K.has(metricKey) ? <MatrizConfusion evaluacion={evaluacion} /> : <PorClaseDeEvaluacion evaluacion={evaluacion} />}
      </div>
    );
  }
  const tabla = filasTasas ? (
    <DrillTasasError evaluacion={evaluacion} resaltar={filasTasas} />
  ) : celdasMatriz ? (
    <MatrizConfusion evaluacion={evaluacion} resaltar={celdasMatriz} />
  ) : null;

  return (
    <div className="flex flex-col gap-4">
      {sinDefinicion ? null : <p className="text-sm text-muted-foreground">{textoQueMide(ayuda)}</p>}
      {tabla ? <ColumnasCalculo tabla={tabla} formula={formula} /> : formula}
    </div>
  );
}

export default CalculoMetrica;
