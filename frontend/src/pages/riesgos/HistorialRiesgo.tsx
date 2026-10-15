/**
 * Historial completo de un riesgo (`GET /risks/{id}/movements`), extraído
 * de `PanelRiesgo.tsx` para que ese fichero se quede por debajo de 9 KB.
 */

import { useRiskMovements } from "@/api/queries-riesgos";
import { formatoFechaLarga, formatoRelativo } from "@/lib/fechas";

export interface HistorialRiesgoProps {
  riskId: number;
}

export function HistorialRiesgo({ riskId }: HistorialRiesgoProps) {
  const movimientos = useRiskMovements(riskId);

  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-md font-semibold">Historial</h2>
      {movimientos.isLoading ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : (movimientos.data?.items.length ?? 0) === 0 ? (
        <p className="text-sm text-muted-foreground">Sin movimientos todavía.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {movimientos.data?.items.map((m) => (
            <li key={m.id} className="rounded-md border border-border p-2.5 text-sm">
              <p>{m.texto}</p>
              <p className="text-xs text-muted-foreground" title={formatoFechaLarga(m.created_at)}>
                {m.actor} · {formatoRelativo(m.created_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
