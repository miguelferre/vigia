/** Bloque de alertas vivas de la pestaña «Comparar». */

import { Link } from "react-router";

import type { AlertaVivaVersion } from "@/api/queries-versiones";
import { Badge } from "@/components/ui/badge";
import { ETIQUETA_MONITOR, metricLabel } from "@/lib/metrics";
import { ETIQUETA_VERSION_MEDIDA, SIN_ALERTAS_VIVAS, SIN_VERSION_ASOCIADA, TITULO_ALERTAS_VIVAS } from "./comparar-textos";

interface Props {
  alertas: readonly AlertaVivaVersion[];
  /** Frase de cabecera que manda la API: «las alertas son del modelo, no de la versión». */
  nota: string;
}

export function AlertasVivas({ alertas, nota }: Props) {
  const cabecera = nota.charAt(0).toUpperCase() + nota.slice(1);
  return (
    <section className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4" data-t10-alertas="">
      <h3 className="text-sm font-semibold">{TITULO_ALERTAS_VIVAS}</h3>
      <p className="text-sm text-muted-foreground">{cabecera}.</p>
      {alertas.length === 0 ? (
        <p className="text-sm text-muted-foreground">{SIN_ALERTAS_VIVAS}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {alertas.map((a) => (
            <li
              key={a.alert_id}
              className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
              data-alerta={a.alert_id}
              data-version={a.model_version_id ?? ""}
            >
              <span className="flex min-w-0 flex-col">
                <Link to={`/alertas/${a.alert_id}`} className="font-medium text-link hover:underline">
                  {a.title}
                </Link>
                <span className="text-xs text-muted-foreground">
                  {ETIQUETA_MONITOR[a.monitor_type as keyof typeof ETIQUETA_MONITOR] ?? a.monitor_type} ·{" "}
                  {metricLabel(a.metric_key)}
                  {a.group_code ? ` · grupo ${a.group_code}` : ""}
                </span>
              </span>
              {a.version_label ? (
                <Badge variant="outline">{ETIQUETA_VERSION_MEDIDA} {a.version_label}</Badge>
              ) : (
                <span className="text-xs text-muted-foreground">{a.motivo ?? SIN_VERSION_ASOCIADA}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
