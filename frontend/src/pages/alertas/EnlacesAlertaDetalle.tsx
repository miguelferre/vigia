/**
 * Fila de enlaces de la cabecera del detalle de alerta: lote, monitor y
 * correlación en el diario. Separada de `detalle.tsx`.
 */

import { Link } from "react-router";

import type { AlertDetail } from "@/api/types";
import { ETIQUETA_MONITOR } from "@/lib/metrics";

interface Props {
  alerta: AlertDetail;
  rutaMonitor: string | undefined;
  correlationId: string | null;
}

export function EnlacesAlertaDetalle({ alerta: a, rutaMonitor, correlationId }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-4 text-md">
      {a.batch_id !== null ? (
        <Link className="underline hover:no-underline" to={`/datos/${a.batch_id}`}>
          Ver el lote
        </Link>
      ) : (
        <span className="text-tertiary">
          {a.status === "retirada" ? "Su lote de origen se borró" : "Sin lote asociado (medida acumulada)"}
        </span>
      )}
      {rutaMonitor ? (
        <Link className="underline hover:no-underline" to={`/monitores/${rutaMonitor}`}>
          Ver el monitor de {ETIQUETA_MONITOR[a.monitor_type].toLowerCase()}
        </Link>
      ) : null}
      {correlationId ? (
        <Link className="underline hover:no-underline" to={`/diario?correlation_id=${correlationId}`}>
          Ver la correlación en el diario
        </Link>
      ) : null}
    </div>
  );
}
