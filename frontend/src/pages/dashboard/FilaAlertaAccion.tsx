/**
 * Fila de «Alertas que requieren acción»: severidad con glifo,
 * título, monitor, lote, estado, antigüedad y «Revisar». Partida de
 * `TablaAlertasAccion.tsx` para que ninguno de los dos pase de 9 KB.
 */

import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import { api } from "@/api/client";
import { qk } from "@/api/queries";
import { useBatches } from "@/api/queries-datos";
import { StateBadge } from "@/components/vigia";
import { useFormatoMetrica } from "@/components/vigia/useFormatoMetrica";
import { ETIQUETA_MONITOR } from "@/lib/metrics";
import { formatoRelativo } from "@/lib/fechas";
import { etiquetaLote, numeroLote, sinRepetirLote } from "@/lib/fases";
import { estadoDeSeveridad, etiquetaSeveridad } from "@/pages/alertas/severidad";
import { etiquetaEtapa } from "@/pages/alertas/etapa";
import type { Alert, EvaluationDetail } from "@/api/types";

/** Umbral de la última medida de la alerta, mismo patrón que la extinta
 * `TarjetaAlerta`: no viaja en `Alert`, hay que leerlo de su
 * evaluación. Con el tope de 5 filas visibles son como mucho 5 peticiones. */
function useUmbralAlerta(alerta: Alert): string | null {
  const { formato } = useFormatoMetrica(alerta.project_id);
  const evaluacion = useQuery({
    queryKey: qk.evaluation(alerta.last_evaluation_id),
    queryFn: () => api.get<EvaluationDetail>(`/evaluations/${alerta.last_evaluation_id}`),
    enabled: alerta.last_evaluation_id !== null,
    staleTime: 10_000,
  });
  const medida = evaluacion.data?.measurements.find(
    (m) => m.metric_key === alerta.metric_key && m.group_code === alerta.group_code,
  );
  if (!medida) return null;
  const partes: string[] = [];
  if (medida.threshold_low !== null) partes.push(`≥ ${formato(medida.metric_key, medida.threshold_low)}`);
  if (medida.threshold_high !== null) partes.push(`≤ ${formato(medida.metric_key, medida.threshold_high)}`);
  return partes.length > 0 ? partes.join(" y ") : null;
}

export function FilaAlerta({ alerta, onRevisar }: { alerta: Alert; onRevisar: () => void }) {
  const umbral = useUmbralAlerta(alerta);
  const { formato } = useFormatoMetrica(alerta.project_id);
  // Lista de lotes del proyecto: misma clave de caché para las 5 filas.
  const lotes = useBatches(alerta.project_id).data?.items;
  const nombreLote =
    alerta.batch_id !== null ? (lotes?.find((b) => b.id === alerta.batch_id)?.dataset_name?.trim() ?? "") : "";
  const faseLote = etiquetaLote(alerta.batch_phase_label) ?? "sin fase";
  const nombreVisible = sinRepetirLote(nombreLote, faseLote);
  return (
    <TableRow>
      <TableCell>
        <StateBadge estado={estadoDeSeveridad(alerta.severity)} texto={etiquetaSeveridad(alerta.severity)} size="sm" />
      </TableCell>
      <TableCell className="max-w-72 whitespace-normal">
        <p className="font-semibold leading-snug">{alerta.title}</p>
        {/* `Event.titulo`/`Alert.title` (backend) ya incluyen valor y umbral
            entre paréntesis en la mayoría de plantillas (`app/events_titulos.py`):
            repetirlos aquí duplicaría el número. Solo se añade la línea
            cuando el título no trae ya una cifra con coma decimal. */}
        {!/\d,\d/.test(alerta.title) ? (
          <p className="text-xs text-muted-foreground">
            {formato(alerta.metric_key, alerta.last_value)}
            {umbral ? ` · umbral ${umbral}` : ""}
          </p>
        ) : null}
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">{ETIQUETA_MONITOR[alerta.monitor_type]}</TableCell>
      <TableCell className="text-sm text-muted-foreground">
        {alerta.batch_seq !== null ? (
          <div className="flex flex-col">
            <span>{`${numeroLote(alerta.batch_seq)} · ${faseLote}`}</span>
            {/* El nombre del lote junto a su número (si no repite la fase). */}
            {nombreVisible ? (
              <span className="max-w-40 truncate text-xs text-tertiary" title={nombreVisible}>
                {nombreVisible}
              </span>
            ) : null}
          </div>
        ) : (
          "n/d"
        )}
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">{etiquetaEtapa(alerta)}</TableCell>
      <TableCell className="text-xs text-tertiary" title={alerta.opened_at}>
        {formatoRelativo(alerta.opened_at)}
      </TableCell>
      <TableCell>
        <Button type="button" variant="outline" size="sm" onClick={onRevisar}>
          Revisar
        </Button>
      </TableCell>
    </TableRow>
  );
}
