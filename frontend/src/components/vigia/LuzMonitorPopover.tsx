/**
 * Detalle de una luz de monitor (`Indicadores.dc.html` «Detalle al
 * clic»): estado con glifo, tres cifras, métrica principal con umbral,
 * última evaluación y enlace al monitor. Partido de `LucesMonitor.tsx` para
 * que ninguno de los dos pase de 9 KB.
 */

import { Link } from "react-router";
import { ArrowRightIcon } from "lucide-react";

import { useBatches } from "@/api/queries-datos";
import type { AlertasAbiertasPorSeveridad, BatchKpi, EstadoMotor, MonitorType } from "@/api/types";
import { ETIQUETA_GLIFO, GLIFO_ESTADO } from "@/lib/iconos";
import { ETIQUETA_MONITOR, MONITOR_A_RUTA, esMedidaEnUnidad, formatoCorto, metricLabel } from "@/lib/metrics";
import { useFormatoMetrica } from "./useFormatoMetrica";
import { formatoRelativo } from "@/lib/fechas";
import { numeroLote } from "@/lib/fases";
import { colorEstado } from "./StateBadge";
import { PopoverContent } from "@/components/ui/popover";

export interface DetalleProps {
  tipo: MonitorType;
  estado: EstadoMotor;
  lote: BatchKpi | null | undefined;
  abiertas: AlertasAbiertasPorSeveridad | null;
  /** Última evaluación del proyecto (cruzadas no tienen lote). */
  ultimaEvaluacion: string | null | undefined;
  /** Para pedir el nombre del lote; sin él solo se ve el número. */
  projectId?: number | null;
  onRatonEntra: () => void;
  onRatonSale: () => void;
}

/** «6 alertas», «1 aviso», «20 correctas»: la cifra del estado va en negrita. */
function Cifra({ n, singular, plural, negrita }: { n: number; singular: string; plural: string; negrita: boolean }) {
  const texto = `${n} ${n === 1 ? singular : plural}`;
  return negrita ? <strong>{texto}</strong> : <>{texto}</>;
}

/** «Última evaluación hace 2 h · lote #3 · lote-03.csv». El nombre sale
 * de la lista de lotes, que se pide aquí y no en `DetallePopover`: este
 * componente solo se monta con el popover abierto. */
function UltimaEvaluacion({ lote, projectId }: { lote: BatchKpi; projectId: number | null | undefined }) {
  const lotes = useBatches(projectId ?? null).data?.items;
  const nombre = lote.batch_id !== null ? lotes?.find((b) => b.id === lote.batch_id)?.dataset_name?.trim() : null;
  return (
    <>
      Última evaluación {formatoRelativo(lote.evaluated_at)} · lote {numeroLote(lote.seq)}
      {nombre ? ` · ${nombre}` : ""}
    </>
  );
}

export function DetallePopover({ tipo, estado, lote, abiertas, ultimaEvaluacion, projectId, onRatonEntra, onRatonSale }: DetalleProps) {
  const { formato } = useFormatoMetrica(projectId);
  const nombre = ETIQUETA_MONITOR[tipo];
  const checks = lote?.checks_by_state?.[tipo];
  const Glifo = GLIFO_ESTADO[estado];
  const metrica = lote?.metrics.find((m) => m.monitor_type === tipo) ?? null;
  const ruta = tipo === "cross" ? "/alertas?monitor=cross" : `/monitores/${MONITOR_A_RUTA[tipo]}`;
  return (
    <PopoverContent
      align="start"
      className="flex w-[236px] flex-col gap-1 rounded-lg p-0 px-3 py-2.5 text-xs shadow-[var(--elevation-pop)]"
      onClick={(e) => e.stopPropagation()}
      onMouseEnter={onRatonEntra}
      onMouseLeave={onRatonSale}
      // Abierto por hover no debe robar el foco (el usuario sigue leyendo la rejilla).
      onOpenAutoFocus={(e) => e.preventDefault()}
    >
      <span className="flex items-center gap-1.5 text-xs font-semibold" style={{ color: colorEstado(estado, "texto") }}>
        <Glifo className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
        {nombre} · {ETIQUETA_GLIFO[estado]}
      </span>
      {/* Alertas y avisos son las abiertas por monitor; correctas, las
          comprobaciones del último lote dentro de umbral. */}
      <span className="tabular-nums">
        <Cifra n={abiertas?.alta ?? 0} singular="alerta" plural="alertas" negrita={estado === "alerta"} /> ·{" "}
        <Cifra n={abiertas?.media ?? 0} singular="aviso" plural="avisos" negrita={estado === "aviso"} /> ·{" "}
        {checks ? <Cifra n={checks.ok} singular="correcta" plural="correctas" negrita={false} /> : "sin comprobaciones"}
      </span>
      {metrica && typeof metrica.value === "number" ? (
        <span className="text-[var(--foreground-tertiary)]">
          {metricLabel(metrica.metric_key)} {formato(metrica.metric_key, metrica.value)}
          {typeof metrica.threshold_value === "number"
            ? ` · umbral ${metrica.threshold_kind === "lower" ? "≥" : "≤"} ${esMedidaEnUnidad(metrica.metric_key) ? formato(metrica.metric_key, metrica.threshold_value) : formatoCorto(metrica.threshold_value)}`
            : ""}
        </span>
      ) : null}
      <span className="text-[var(--foreground-tertiary)]">
        {tipo === "cross"
          ? `Última comprobación ${formatoRelativo(ultimaEvaluacion)}`
          : lote
            ? <UltimaEvaluacion lote={lote} projectId={projectId} />
            : "Sin evaluar"}
      </span>
      <Link to={ruta} className="inline-flex items-center gap-1 font-medium hover:underline">
        {tipo === "cross" ? "Ver alertas" : "Ver monitor"}
        <ArrowRightIcon className="size-3" aria-hidden="true" />
      </Link>
    </PopoverContent>
  );
}
