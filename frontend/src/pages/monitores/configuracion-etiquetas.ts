/**
 * Vocabulario en español de las claves técnicas de `config`:
 * etiqueta y línea de ayuda por clave, para `ConfigSimpleEditor`
 * (`configuracion-campos.tsx`). Una clave sin entrada aquí se enseña en
 * crudo, como antes. `OPCIONES_CONFIG` marca las claves con
 * vocabulario cerrado (por ahora solo `baseline_mode`): se editan con un
 * selector, no con texto libre.
 */

export interface EtiquetaConfig {
  etiqueta: string;
  ayuda: string;
}

export const ETIQUETA_CONFIG: Record<string, EtiquetaConfig> = {
  // Equidad (`core/schema.py::FairnessConfig`)
  min_records: {
    etiqueta: "Muestra mínima de la ventana",
    ayuda: "Registros que hacen falta en la ventana antes de evaluar el monitor.",
  },
  min_group: {
    etiqueta: "Mínimo por grupo",
    ayuda: "Registros mínimos de un grupo para que su medida cuente.",
  },
  min_positives: {
    etiqueta: "Mínimo de resultados favorables por grupo (valor frágil por debajo)",
    ayuda: "Por debajo de este número, el resultado del grupo se marca como valor frágil.",
  },
  window_step: {
    etiqueta: "Paso de la ventana deslizante",
    ayuda: "Cada cuántos lotes se desliza la ventana de evaluación.",
  },
  interval_windows_max: {
    etiqueta: "Ventanas del intervalo (estado inestable)",
    ayuda: "Ventanas anteriores que entran en el intervalo que puede marcar el estado inestable.",
  },
  label_min_records: {
    etiqueta: "Mínimo de registros con etiqueta",
    ayuda: "Registros con etiqueta de verdad que hacen falta para evaluar la calidad.",
  },
  // Calidad (`core/schema.py::QualityConfig`, más `primary_metric`)
  min_feedback: {
    etiqueta: "Mínimo de registros con etiqueta",
    ayuda: "Registros con etiqueta de verdad que hacen falta para evaluar la calidad.",
  },
  primary_metric: {
    etiqueta: "Métrica principal",
    ayuda: "Métrica de calidad que se resalta en el cuadro y en el monitor.",
  },
  // Deriva (`core/schema.py::DriftConfig`)
  psi_bins: {
    etiqueta: "Tramos del PSI",
    ayuda: "Tramos en que se divide cada variable numérica para calcular el PSI.",
  },
  confidence_bins: {
    etiqueta: "Tramos del histograma de confianza",
    ayuda: "Tramos del histograma que compara la confianza de la línea base y el lote.",
  },
  baseline_mode: {
    etiqueta: "Línea base de referencia",
    ayuda: "Con qué se compara cada lote: la línea base congelada o el lote anterior.",
  },
  // Alertas cruzadas (`human/cross_alerts.py::CrossConfig`)
  z_alert: {
    etiqueta: "Umbral z de alerta",
    ayuda: "Desviaciones típicas por encima de la media que activan la alerta cruzada.",
  },
  model_error_z: {
    etiqueta: "Umbral z del error del modelo",
    ayuda: "Desviaciones típicas de la tasa de error del modelo que cuentan como significativas.",
  },
  min_clinician: {
    etiqueta: "Mínimo por profesional",
    ayuda: "Decisiones mínimas de un profesional para entrar en la comparación entre profesionales.",
  },
  chi2_p: {
    etiqueta: "p del test chi cuadrado",
    ayuda: "Umbral de significación: por debajo, la diferencia entre profesionales activa la alerta.",
  },
  min_expected: {
    etiqueta: "Frecuencia esperada mínima",
    ayuda: "Frecuencia esperada mínima por celda para que el test chi cuadrado sea fiable.",
  },
};

/** Claves cuyo valor es un vocabulario cerrado: selector con estas opciones, no texto libre. */
export const OPCIONES_CONFIG: Record<string, Record<string, string>> = {
  baseline_mode: {
    frozen: "Congelada",
    previous_batch: "Lote anterior",
  },
};
