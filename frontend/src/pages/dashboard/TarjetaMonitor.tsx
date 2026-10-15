/**
 * Una tarjeta de monitor del cuadro (artboard
 * `Main.dc.html`): línea superior de 4 px con el color del estado, nombre y
 * estado, tres cifras (alertas, avisos, correctas) y el enlace al monitor.
 * `TarjetasMonitor` monta cuatro con sus datos; aquí solo la presentación.
 */

import type { LucideIcon } from "lucide-react";
import { ArrowRightIcon } from "lucide-react";
import { Link } from "react-router";

import { Card } from "@/components/ui/card";
import { colorEstado, InfoTooltip } from "@/components/vigia";
import { GLIFO_ESTADO } from "@/lib/iconos";
import { ETIQUETA_ESTADO } from "@/lib/metrics";
import { formatoRelativo } from "@/lib/fechas";
import type { EstadoMotor } from "@/api/types";

interface CifraProps {
  valor: number | "n/d";
  etiqueta: string;
  color: string;
  ayuda?: { titulo: string; queMide: string };
}

function Cifra({ valor, etiqueta, color, ayuda }: CifraProps) {
  const cero = valor === "n/d" || valor === 0;
  return (
    <div className="flex flex-col gap-1">
      <span
        className="text-[28px] leading-none font-semibold tabular-nums"
        style={{ color: cero ? "var(--state-nodata)" : color }}
      >
        {valor}
      </span>
      <span className="flex items-center gap-1 text-[10px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">
        {etiqueta}
        {ayuda ? <InfoTooltip titulo={ayuda.titulo} queMide={ayuda.queMide} /> : null}
      </span>
    </div>
  );
}

export interface TarjetaMonitorProps {
  nombre: string;
  estado: EstadoMotor;
  alta: number;
  media: number;
  correctas: number | "n/d";
  ultimaEvaluacion: string | null;
  textoUltimaEvaluacion: string;
  ruta: string;
  textoEnlace: string;
  textoAyudaCorrectas: string;
}

export function TarjetaMonitor({
  nombre,
  estado,
  alta,
  media,
  correctas,
  ultimaEvaluacion,
  textoUltimaEvaluacion,
  ruta,
  textoEnlace,
  textoAyudaCorrectas,
}: TarjetaMonitorProps) {
  const Glifo: LucideIcon = GLIFO_ESTADO[estado];
  return (
    <Card
      className="flex flex-col gap-3 rounded-lg px-3.5 py-3"
      style={{ borderTop: `4px solid ${colorEstado(estado, "relleno")}` }}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <span className="min-w-0 truncate text-[13px] font-semibold">{nombre}</span>
        <span
          className="inline-flex shrink-0 items-center gap-1.5 text-xs font-semibold"
          style={{ color: colorEstado(estado, "texto") }}
        >
          <Glifo className="size-4" strokeWidth={1.5} aria-hidden="true" />
          {ETIQUETA_ESTADO[estado]}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Cifra valor={alta} etiqueta="Alertas" color="var(--state-alert)" />
        <Cifra valor={media} etiqueta="Avisos" color="var(--state-warn)" />
        <Cifra
          valor={correctas}
          etiqueta="Correctas"
          color="var(--state-ok)"
          ayuda={{ titulo: "Comprobaciones dentro de umbral", queMide: textoAyudaCorrectas }}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <span className="min-w-0 truncate text-xs text-tertiary">
          {textoUltimaEvaluacion} {formatoRelativo(ultimaEvaluacion)}
        </span>
        <Link to={ruta} className="inline-flex shrink-0 items-center gap-1 text-[13px] font-medium whitespace-nowrap">
          {textoEnlace}
          <ArrowRightIcon className="size-4" aria-hidden="true" />
        </Link>
      </div>
    </Card>
  );
}
