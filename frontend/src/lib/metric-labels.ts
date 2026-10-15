import { CAPACIDADES } from "@/lib/tipo-tarea";
import { NOMBRES_CRUZADAS } from "@/pages/capa-humana/cruzadas-nombres";

/**
 * Vocabulario de métricas: etiqueta en español de cada `metric_key`.
 *
 * `METRIC_LABELS` es copia literal de `METRIC_LABELS` en
 * `src/vigia/app/services/alerting.py`. Lo que no esté en el
 * diccionario se muestra con su clave tal cual, igual que hace el backend.
 * Hay que verificar la paridad con el backend al cambiar este fichero.
 */

export const METRIC_LABELS: Record<string, string> = {
  fairness_value: "Impacto dispar (escala 0-100)",
  false_negative_rate_difference: "Diferencia de tasa de falsos negativos",
  accuracy: "Exactitud",
  confidence_drift_score: "Deriva de confianza",
  feature_drift_score: "Deriva de características",
  // Reglas cruzadas CX-1 a CX-6 y `human_review_zero`: un solo sitio.
  ...NOMBRES_CRUZADAS,
};

/**
 * Etiquetas que faltan en `METRIC_LABELS` del backend (huecos detectados en
 * el cuadro de mando y en /alertas: se ven sin traducir). NO forman parte de
 * la copia literal de `src/vigia/app/services/alerting.py:53-62`; es un
 * parche temporal solo de frontend hasta decidir si se añaden
 * también al backend. No fusionar dentro de `METRIC_LABELS` para no romper
 * la garantía de paridad byte a byte con el backend.
 *
 * Las 18 entradas desde `statistical_parity_difference` hasta
 * `output_metadata_drift_score` entraron con la rejilla de monitores
 * (enseña todas las métricas de un monitor a la vez). Texto tomado tal
 * cual de la columna "Etiqueta UI" del glosario de métricas,
 * salvo `input_metadata_drift_score` y `output_metadata_drift_score`, que el
 * glosario deja sin etiquetar: su nombre sale de `src/vigia/core/drift.py` y
 * `thresholds.py` y de la decisión de dejarlas
 * fuera de v1 por ser de modelos de texto aunque tengan umbral configurado.
 * `false_positive_rate_difference`, `false_discovery_rate_difference` y
 * `false_omission_rate_difference` se reescriben respecto al glosario (que
 * usa las siglas FPR/FDR/FOR) para leerse como familia junto con
 * `false_negative_rate_difference` y `error_rate_difference`.
 *
 * se retira cuando `content/` (metricas-ayuda.json, servido por
 * `GET /api/content/metricas`) cubra sus 18 claves. Hasta entonces convive
 * con el ⓘ de `InfoTooltip`, que lee de `content/` para lo que ya está.
 */
export const METRIC_LABELS_EXTRA: Record<string, string> = {
  area_under_roc: "Área bajo la curva ROC",
  prediction_drift_score: "Deriva de las predicciones",
  gini_coefficient: "Coeficiente de Gini",
  matthews_correlation_coefficient: "Coeficiente de correlación de Matthews",
  recall: "Sensibilidad (recall)",
  // Monitor quality, sin umbral: se leían con la clave cruda en Comparar.
  label_rate: "Tasa de etiqueta favorable",
  prediction_rate: "Tasa de predicción favorable",
  true_positive_rate: "Tasa de verdaderos positivos",

  // Familia de diferencias de tasa del monitor fairness (junto con
  // false_negative_rate_difference en METRIC_LABELS).
  statistical_parity_difference: "Diferencia de paridad estadística",
  false_positive_rate_difference: "Diferencia de tasa de falsos positivos",
  false_discovery_rate_difference: "Diferencia de tasa de falsos descubrimientos",
  false_omission_rate_difference: "Diferencia de tasa de falsos omitidos",
  error_rate_difference: "Diferencia de tasa de error",
  average_odds_difference: "Diferencia media de falsos positivos y sensibilidad",
  average_abs_odds_difference: "Diferencia absoluta media de falsos positivos y sensibilidad",
  impact_score: "Puntuación de impacto",

  // Monitor quality.
  area_under_pr: "Área bajo la curva precisión-sensibilidad",
  false_positive_rate: "Tasa de falsos positivos",
  precision: "Precisión",
  f1_measure: "Medida F1",
  log_loss: "Pérdida logarítmica",
  label_skew: "Sesgo de etiqueta",
  brier_score: "Puntuación de Brier",

  // Monitor explain: el dato del paso 6 y 15 de la demo guiada
  // (`PanelDato`) y cualquier medida del monitor la enseñan con este nombre.
  explain_stability_ndcg: "Estabilidad de la explicación",
  // No es una medida del motor: la calcula el frontend con
  // `GET /batches/{id}/composition` (paso 14 de la demo guiada).
  composicion_grupo_supervisado_pct: "Proporción del grupo supervisado (%)",

  // Monitor drift_v2.
  model_quality_score: "Desviación en calidad modelo",
  // Sin etiqueta en el glosario (fuera de v1, modelos de texto/LLM).
  input_metadata_drift_score: "Deriva de metadatos de entrada",
  output_metadata_drift_score: "Deriva de metadatos de salida",

  // `human_review_zero` sale de `NOMBRES_CRUZADAS`, como las CX-n.

  // Regresión: copia de `etiqueta` en `metricas-ayuda.json`.
  mean_absolute_error: "Error absoluto medio (MAE)",
  root_mean_squared_error: "Raíz del error cuadrático medio (RMSE)",
  r2: "Coeficiente de determinación (R²)",
  mean_error: "Sesgo medio (error medio)",
  mean_squared_error: "Error cuadrático medio (MSE)",
  median_absolute_error: "Error absoluto mediano",
  mean_absolute_error_difference: "Diferencia de error entre grupos",
  mean_absolute_error_ratio: "Razón de error entre grupos",
  mean_error_difference: "Diferencia de sesgo entre grupos",
};

/** Etiqueta de una métrica; su clave si no está en ningún diccionario. */
export function metricLabel(clave: string): string {
  return METRIC_LABELS[clave] ?? METRIC_LABELS_EXTRA[clave] ?? clave;
}

/**
 * en multiclase las claves de calidad de siempre llevan el
 * promedio macro (cada clase contra el resto, sin ponderar). La clave no
 * cambia; la etiqueta lo dice para que «Precisión» no se lea como binaria.
 */
const ETIQUETAS_MULTICLASE: Record<string, string> = {
  precision: "Precisión (macro)",
  recall: "Sensibilidad (recall, macro)",
  true_positive_rate: "Tasa de verdaderos positivos (macro)",
  false_positive_rate: "Tasa de falsos positivos (macro)",
  f1_measure: "Medida F1 (macro)",
  area_under_roc: "Área bajo la curva ROC (macro)",
  area_under_pr: "Área bajo la curva precisión-sensibilidad (macro)",
  label_skew: "Sesgo de etiqueta (clases favorables)",
};

/** Etiqueta de una métrica según el tipo de tarea; sin tipo o en binario, `metricLabel`. */
export function metricLabelPorTipo(clave: string, tipo: string | null | undefined): string {
  if (tipo && tipo in CAPACIDADES && CAPACIDADES[tipo as keyof typeof CAPACIDADES].bloqueAyuda === "multiclase") return ETIQUETAS_MULTICLASE[clave] ?? metricLabel(clave);
  return metricLabel(clave);
}

/**
 * en una medida por clase (`group_code = "clase:<valor>"`) la métrica es
 * de esa clase, sin promedio macro, y las dos tasas son la proporción de la
 * clase (no una tasa «favorable»). Las demás claves, con su etiqueta de siempre.
 */
const ETIQUETAS_DE_CLASE: Record<string, string> = {
  label_rate: "Proporción de casos reales de la clase",
  prediction_rate: "Proporción de predicciones de la clase",
};

export function metricLabelDeClase(clave: string): string {
  return ETIQUETAS_DE_CLASE[clave] ?? metricLabel(clave);
}
