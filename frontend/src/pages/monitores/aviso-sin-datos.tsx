/**
 * Cabecera del monitor que enumera las métricas en `sin_datos` con su
 * motivo, leyendo `result.details.metricas_sin_datos` de la evaluación. El
 * estado del monitor sale de las métricas que sí se evaluaron; esto
 * dice cuáles se quedaron sin valor y por qué, para que un `ok` no esconda un
 * hueco. Fuera de `cabecera.tsx` por tamaño.
 *
 * En multiclase hay dos clases de «sin datos» que son un
 * motivo y no un fallo. «Umbral pendiente de la línea base» (los titulares
 * esperan a la línea base) se enseña como un aviso tranquilo, y las medidas
 * por clase sin datos (clase rara en la ventana) se agrupan por motivo con los
 * nombres de clase, en vez de una línea por clase y métrica.
 */

import { InfoIcon } from "lucide-react";

import { useTipoTarea } from "@/hooks/useTipoTarea";
import { metricLabelPorTipo } from "@/lib/metrics";
import { claseDeGrupo, esGrupoClase } from "@/lib/tipo-tarea";
import { calidadSinFabrica } from "./regresion-datos";
import { useEvaluationDetail } from "./usarEvaluacion";

interface MetricaSinDatos {
  metric_key: string;
  group_code?: string | null;
  motivo?: string | null;
}

function leerMetricas(details: unknown): MetricaSinDatos[] {
  if (details === null || typeof details !== "object") return [];
  const lista = (details as { metricas_sin_datos?: unknown }).metricas_sin_datos;
  if (!Array.isArray(lista)) return [];
  return lista.filter(
    (m): m is MetricaSinDatos =>
      m !== null && typeof m === "object" && typeof (m as { metric_key?: unknown }).metric_key === "string",
  );
}

const PENDIENTE = "pendiente de la línea base";

/** Medidas por clase sin datos, agrupadas por motivo: `motivo -> clases`. */
function agruparPorMotivo(porClase: MetricaSinDatos[]): { motivo: string; clases: string[] }[] {
  const mapa = new Map<string, Set<string>>();
  for (const m of porClase) {
    let motivo = m.motivo ?? "sin motivo";
    let nombre = claseDeGrupo(m.group_code) ?? "";
    // «clase con 12 filas en la ventana, se piden al menos 20» se agrupa por el mínimo y la clase lleva su recuento.
    const rara = /^clase con (\d+) filas en la ventana, se piden al menos (\d+)$/.exec(motivo);
    if (rara) {
      motivo = `clase con menos de ${rara[2]} casos reales en la ventana`;
      nombre = `${nombre} (${rara[1]})`;
    }
    const set = mapa.get(motivo) ?? new Set<string>();
    set.add(nombre);
    mapa.set(motivo, set);
  }
  return Array.from(mapa, ([motivo, clases]) => ({ motivo, clases: Array.from(clases) }));
}

export function AvisoMetricasSinDatos({ evaluationId }: { evaluationId: number | null }) {
  const detalle = useEvaluationDetail(evaluationId);
  const { tipo, caps } = useTipoTarea(detalle.data?.project_id ?? null);
  const todas = leerMetricas(detalle.data?.result?.details);
  if (todas.length === 0) return null;
  const metricas = todas.filter((m) => !esGrupoClase(m.group_code));
  const porClase = todas.filter((m) => esGrupoClase(m.group_code));
  // «Umbral pendiente de la línea base»: sin umbral de fábrica en multiclase ni en regresión.
  const sinFabrica = calidadSinFabrica(caps, "quality");
  const pendientes = sinFabrica ? metricas.filter((m) => m.motivo?.includes(PENDIENTE)) : [];
  const origenUmbrales = caps?.metricas === "regresion" ? "En una regresión" : "En multiclase";
  const resto = metricas.filter((m) => !pendientes.includes(m));
  const etiqueta = (clave: string) => metricLabelPorTipo(clave, tipo);

  return (
    <div
      data-testid="metricas-sin-datos"
      className="flex flex-col gap-1 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs"
    >
      {resto.length > 0 ? (
        <>
          <p className="inline-flex items-center gap-1.5 font-medium">
            <InfoIcon className="size-3.5 shrink-0" aria-hidden="true" />
            {resto.length === 1 ? "1 métrica sin datos en esta evaluación" : `${resto.length} métricas sin datos en esta evaluación`}
          </p>
          <ul className="flex flex-col gap-0.5 pl-5">
            {resto.map((m) => (
              <li key={`${m.metric_key}:${m.group_code ?? ""}`} className="list-disc [overflow-wrap:anywhere]">
                <span className="font-medium">{etiqueta(m.metric_key)}</span>
                {m.group_code ? <span className="text-muted-foreground"> ({m.group_code})</span> : null}
                {m.motivo ? <span className="text-muted-foreground">: {m.motivo}</span> : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {pendientes.length > 0 ? (
        <p className="inline-flex items-start gap-1.5 [overflow-wrap:anywhere]" data-testid="umbral-pendiente">
          <InfoIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>
            <span className="font-medium">Umbral pendiente de la línea base:</span>{" "}
            {pendientes.map((m) => etiqueta(m.metric_key)).join(", ")}. {origenUmbrales} no hay umbral de fábrica: se
            fija al congelar la línea base. Hasta entonces estas métricas se calculan, pero no se comparan con nada ni
            abren alertas.
          </span>
        </p>
      ) : null}
      {porClase.length > 0 ? (
        <div className="flex flex-col gap-0.5" data-testid="clases-sin-datos">
          <p className="inline-flex items-center gap-1.5 font-medium">
            <InfoIcon className="size-3.5 shrink-0" aria-hidden="true" />
            Medidas por clase sin datos
          </p>
          <ul className="flex flex-col gap-0.5 pl-5">
            {agruparPorMotivo(porClase).map(({ motivo, clases }) => (
              <li key={motivo} className="list-disc [overflow-wrap:anywhere]">
                <span className="text-muted-foreground">{motivo}: </span>
                <span className="font-medium">{clases.join(", ")}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
