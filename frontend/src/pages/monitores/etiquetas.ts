/**
 * Traducciones propias de `pages/monitores/`:
 * claves de `config_snapshot` del detalle de evaluación. La etiqueta del
 * lote viene de `lib/fases.ts`, único traductor.
 */

export { etiquetaLote } from "@/lib/fases";

/** Claves conocidas de `config_snapshot` (`core/engine.py:MonitorSettings`), a texto de usuario. */
export const ETIQUETA_CONFIG: Record<string, string> = {
  "fairness.min_records": "Equidad · mínimo de registros (predicción)",
  "fairness.label_min_records": "Equidad · mínimo de registros con etiqueta",
  "fairness.min_group": "Equidad · mínimo por grupo",
  "fairness.min_positives": "Equidad · mínimo de positivos por grupo",
  "fairness.window_step": "Equidad · paso de la ventana deslizante",
  "fairness.interval_windows_max": "Equidad · tope de ventanas para el intervalo",
  "quality.min_feedback": "Calidad · mínimo de registros con etiqueta",
  "drift.psi_bins": "Deriva · tramos del índice de estabilidad (PSI)",
  "drift.confidence_bins": "Deriva · tramos del histograma de confianza",
  "drift.baseline_mode": "Deriva · modo de línea base",
};

const ETIQUETA_VALOR: Record<string, string> = {
  frozen: "Congelada",
  previous_batch: "Lote anterior",
};

export interface FilaConfig {
  clave: string;
  etiqueta: string;
  valor: string;
}

/**
 * Aplana `config_snapshot` (`MonitorSettings.model_dump`, dos niveles:
 * `fairness/quality/drift.<campo>`) a las filas con etiqueta conocida; el
 * resto (incluido `thresholds`, una lista) queda para el `<details>` técnico.
 */
export function filasConfigConocidas(config: Record<string, unknown> | null | undefined): FilaConfig[] {
  if (!config) return [];
  const filas: FilaConfig[] = [];
  for (const [clave, etiqueta] of Object.entries(ETIQUETA_CONFIG)) {
    const [seccion, campo] = clave.split(".");
    const seccionValor = config[seccion as string];
    if (!seccionValor || typeof seccionValor !== "object") continue;
    const valor = (seccionValor as Record<string, unknown>)[campo as string];
    if (valor === null || valor === undefined) continue;
    if (typeof valor === "string" || typeof valor === "number" || typeof valor === "boolean") {
      const texto = typeof valor === "string" ? (ETIQUETA_VALOR[valor] ?? valor) : String(valor);
      filas.push({ clave, etiqueta, valor: texto });
    }
  }
  return filas;
}
