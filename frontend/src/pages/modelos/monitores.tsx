/**
 * Pestaña «Monitores» de `/modelos/:id`: una tarjeta por monitor con su
 * estado. Equidad, calidad, deriva y explicabilidad
 * usan `MonitorTarjeta` (umbrales, grupo supervisado y «Configurar»); alertas
 * cruzadas se queda con la tarjeta simple de antes.
 */

import { useProjectState, useMonitors } from "@/api/queries";
import { StateBadge } from "@/components/vigia";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ETIQUETA_MONITOR, formatoFecha } from "@/lib/metrics";

import { MonitorTarjeta } from "./monitor-tarjeta";

interface Props {
  projectId: number;
}

export default function MonitoresTab({ projectId }: Props) {
  const { data: monitores, isLoading } = useMonitors(projectId);
  const { data: estado } = useProjectState(projectId);

  if (isLoading) {
    return <p className="pt-4 text-sm text-muted-foreground" data-loading="true">Cargando monitores…</p>;
  }

  return (
    <div id="monitores" className="grid scroll-mt-20 grid-cols-1 gap-4 pt-4 sm:grid-cols-2 lg:grid-cols-3">
      {(monitores?.items ?? []).map((m) => {
        const info = estado?.monitors.find((e) => e.type === m.type);
        if (m.type === "cross") {
          return (
            <Card key={m.id}>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-sm">{ETIQUETA_MONITOR[m.type]}</CardTitle>
                {info?.worst_state ? <StateBadge estado={info.worst_state} size="sm" /> : null}
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm text-muted-foreground">
                <p>{m.enabled ? "Activado" : "Desactivado"}</p>
                <p>Última evaluación: {formatoFecha(info?.last_evaluated_at)}</p>
                <span className="text-xs italic">Su detalle está en Capa humana</span>
              </CardContent>
            </Card>
          );
        }
        return (
          <MonitorTarjeta
            key={m.id}
            monitor={m}
            projectId={projectId}
            info={info}
            qualityPrimaryMetric={estado?.quality_primary_metric}
          />
        );
      })}
    </div>
  );
}
