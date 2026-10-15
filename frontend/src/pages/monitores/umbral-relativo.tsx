/**
 * Nota de un umbral relativo a la prevalencia en la hoja «Configurar». El umbral de fábrica de `area_under_pr` no es un valor de la
 * métrica: es la fracción (0,8) de lo que la línea base mejora sobre la
 * prevalencia. El número editable es esa fracción; el límite que se evalúa lo
 * resuelve el motor con la línea base y llega en `threshold_low` de la última
 * medida, con la prevalencia y el AUC-PR de la línea base en
 * `extra.umbral_relativo`.
 *
 * Esta nota lee esa última medida y dice las dos cosas: qué es lo que se
 * cambia y cuál es el límite que se está aplicando hoy.
 */

import { useTimeline } from "@/api/queries";
import { formatoNumero } from "@/lib/metrics";

import { useEvaluationDetail } from "./usarEvaluacion";

export interface NotaUmbralRelativoProps {
  projectId: number;
  metricKey: string;
}

export function NotaUmbralRelativo({ projectId, metricKey }: NotaUmbralRelativoProps) {
  const serieQ = useTimeline(projectId, "quality", [metricKey]);
  const globales = (serieQ.data?.items ?? [])
    .filter((p) => p.group_code === null)
    .sort((a, b) => a.ts.localeCompare(b.ts));
  const ultimo = globales[globales.length - 1] ?? null;
  const detalleQ = useEvaluationDetail(ultimo?.evaluation_id ?? null);
  const medida = detalleQ.data?.measurements.find((m) => m.metric_key === metricKey && m.group_code === null);
  const rel = medida?.extra?.umbral_relativo;
  const extra = rel !== null && typeof rel === "object" ? (rel as Record<string, unknown>) : null;
  const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
  const prevalencia = num(extra?.prevalencia);
  const aucBase = num(extra?.auc_pr_linea_base);

  return (
    <p className="text-xs text-muted-foreground" data-testid="nota-umbral-relativo">
      Relativo a la prevalencia: el número de arriba no es el límite, es la parte de la mejora de la línea base sobre
      la prevalencia que se exige.{" "}
      {ultimo?.threshold_low != null ? (
        <>
          Límite que se evalúa ahora: <span className="font-semibold text-foreground">{formatoNumero(ultimo.threshold_low, 3)}</span>
          {prevalencia !== null && aucBase !== null
            ? ` (prevalencia ${formatoNumero(prevalencia, 3)}, AUC-PR de la línea base ${formatoNumero(aucBase, 3)}).`
            : "."}
        </>
      ) : (
        "Sin límite todavía: se resuelve al congelar la línea base."
      )}
    </p>
  );
}

export default NotaUmbralRelativo;
