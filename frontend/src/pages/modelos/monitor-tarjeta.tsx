/**
 * Tarjeta de un monitor en la pestaña «Monitores» de `/modelos/:id`:
 * además del estado, enseña los umbrales configurados,
 * el grupo supervisado de equidad y un botón «Configurar» que abre la misma
 * hoja que `/monitores/<tipo>` (`ConfiguracionMonitor`), sin tener que pasar
 * por esa pantalla primero. La de alertas cruzadas no usa esta tarjeta: se
 * queda como estaba en `monitores.tsx` (sin umbrales ni configuración).
 */

import { useState } from "react";
import { Link } from "react-router";

import type { Monitor, MonitorEstado } from "@/api/types";
import { MetricLabel, StateBadge } from "@/components/vigia";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ETIQUETA_MONITOR, MONITOR_A_RUTA, formatoFecha } from "@/lib/metrics";
import { ICONO_MONITOR } from "@/lib/iconos";
import { useCan } from "@/session/session";
import { ChipGrupos } from "@/pages/monitores/cabecera";
import { ConfiguracionMonitor } from "@/pages/monitores/configuracion";
import { extraerUmbrales } from "@/pages/monitores/tipos";
import { umbralSinEfectoEnMulticlase } from "@/pages/monitores/umbrales-efectivos";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { metricaPrincipal, ordenarPorPrincipal, textoUmbral } from "./monitor-tarjeta-principal";

/** Máximo de líneas de umbral antes de resumir con «y N más». */
const TOPE_UMBRALES = 4;

export interface MonitorTarjetaProps {
  monitor: Monitor;
  projectId: number;
  /** Estado operativo del monitor (`GET /projects/{id}/state`), si ya cargó. */
  info: MonitorEstado | undefined;
  /** `ProjectState.quality_primary_metric`: métrica principal ya resuelta por el backend. */
  qualityPrimaryMetric: string | undefined;
}

export function MonitorTarjeta({ monitor: m, projectId, info, qualityPrimaryMetric }: MonitorTarjetaProps) {
  const puedeConfig = useCan("config");
  const [configAbierta, setConfigAbierta] = useState(false);

  const Icono = ICONO_MONITOR[m.type];
  const ruta = MONITOR_A_RUTA[m.type];
  const { tipo, caps, unidad } = useTipoTarea(projectId);
  // Hasta conocer el tipo de tarea no se listan umbrales (evita el parpadeo a binario).
  const cargandoTipo = caps === undefined;
  const todosUmbrales = cargandoTipo ? [] : extraerUmbrales(m.thresholds);
  // En multiclase los umbrales de fábrica no se evalúan; solo se listan los que valen.
  const sinFabricaMulticlase = caps?.matriz === "kxk" && m.type === "quality";
  const principal = caps ? metricaPrincipal(m.type, caps, qualityPrimaryMetric) : null;
  const sinOrdenar = cargandoTipo ? [] : sinFabricaMulticlase ? todosUmbrales.filter((u) => !umbralSinEfectoEnMulticlase(u)) : todosUmbrales;
  const umbrales = caps ? ordenarPorPrincipal(sinOrdenar, principal, caps) : sinOrdenar;
  const sinEfecto = todosUmbrales.length - umbrales.length;
  const mostrados = umbrales.slice(0, TOPE_UMBRALES);
  const resto = umbrales.length - mostrados.length;

  return (
    <Card className="flex flex-col">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div className="flex items-center gap-2">
          <Icono className="size-4 text-muted-foreground" strokeWidth={1.5} aria-hidden="true" />
          <CardTitle className="text-sm">{ETIQUETA_MONITOR[m.type]}</CardTitle>
        </div>
        {info?.worst_state ? <StateBadge estado={info.worst_state} size="sm" /> : null}
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3 text-sm text-muted-foreground">
        {sinFabricaMulticlase && sinEfecto > 0 ? (
          <p className="text-xs">
            {mostrados.length === 0
              ? "Sin umbrales todavía: en multiclase no hay umbral de fábrica, se fija desde la línea base."
              : `${sinEfecto} métricas sin umbral: en multiclase no hay umbral de fábrica, se fija desde la línea base.`}
          </p>
        ) : null}
        {mostrados.length > 0 ? (
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Umbrales</span>
            {mostrados.map((u) => {
              const esPrincipal = u.metric_key === principal;
              return (
                <p key={`${u.metric_key}-${u.kind}`} className="text-sm text-foreground">
                  <MetricLabel metrica={u.metric_key} tipo={tipo} />
                  {" · "}
                  {textoUmbral(u, caps?.unidad ? unidad : undefined)}
                  {esPrincipal ? <span className="text-xs text-muted-foreground"> · principal</span> : null}
                </p>
              );
            })}
            {resto > 0 ? (
              ruta ? (
                <Link to={`/monitores/${ruta}`} className="w-fit text-xs underline underline-offset-2">
                  y {resto} más
                </Link>
              ) : (
                <span className="text-xs">y {resto} más</span>
              )
            ) : null}
          </div>
        ) : null}

        {/* El chip no envuelve texto (`whitespace-nowrap` del Badge base) y a
         * 1024 px (rejilla a 3 columnas) es más ancho que la tarjeta: se
         * contiene con scroll horizontal propio en vez de invadir la
         * siguiente tarjeta. No se toca `ChipGrupos`. */}
        <div className="max-w-full overflow-x-auto">
          <ChipGrupos monitorType={m.type} monitor={m} />
        </div>

        <div className="mt-auto flex flex-col gap-2 pt-1">
          <p>{m.enabled ? "Activado" : "Desactivado"}</p>
          <p>Última evaluación: {formatoFecha(info?.last_evaluated_at)}</p>
          <div className="flex flex-wrap gap-2">
            {ruta ? (
              <Button asChild size="sm" variant="outline" className="w-fit">
                <Link to={`/monitores/${ruta}`}>Ver monitor</Link>
              </Button>
            ) : (
              <span className="text-xs italic">
                Su detalle está en {m.type === "explain" ? "Explicabilidad" : "Capa humana"}
              </span>
            )}
            {puedeConfig ? (
              <Button size="sm" variant="outline" className="w-fit" onClick={() => setConfigAbierta(true)}>
                Configurar
              </Button>
            ) : null}
          </div>
        </div>
      </CardContent>

      {puedeConfig ? (
        <ConfiguracionMonitor monitor={m} projectId={projectId} open={configAbierta} onOpenChange={setConfigAbierta} />
      ) : null}
    </Card>
  );
}
