/**
 * Luces de monitor: cuatro círculos con el
 * icono del monitor, el estado combinado (`estadoMonitor`) como color de
 * relleno y una pastilla con el glifo y la cifra cuando hay alerta o aviso.
 * Sustituye a las pastillas con texto de `pastillas-monitor.tsx`: sin nombre escrito, un símbolo por estado. Compartido
 * por la tarjeta de `/modelos`; el cuadro usa sus propias tarjetas de
 * monitor, no esto. El detalle es un popover que se abre al pasar el ratón
 * («que sea al hacer hover»), con un retardo
 * corto para no abrirlo al cruzar la fila, y se queda abierto mientras el
 * ratón esté en la luz o dentro del propio popover (para llegar a «Ver
 * monitor»); el clic y el foco de teclado lo abren igual, sin navegar
 * (`stopPropagation`): la tarjeta entera es un enlace al cuadro. Sin
 * `title` nativo: duplicaba el detalle con un tooltip del navegador.
 */

import { useRef, useState } from "react";
import type { EstadoMotor, MonitorType, ProjectSummary } from "@/api/types";
import { GLIFO_ESTADO, ICONO_MONITOR } from "@/lib/iconos";
import { ETIQUETA_MONITOR } from "@/lib/metrics";
import { estadoMonitor } from "@/lib/estado-monitor";
import { colorEstado } from "./StateBadge";
import { DetallePopover } from "./LuzMonitorPopover";
import { Popover, PopoverTrigger } from "@/components/ui/popover";

// Los cuatro monitores con luz propia. Sin `explain`: la explicabilidad tiene su
// pantalla y su tarjeta de estabilidad, y ya no
// viaja en `states_by_monitor` ni en `alerts_open_by_monitor`.
const MONITORES = ["fairness", "quality", "drift", "cross"] as const;

export interface LucesMonitorProps {
  summary: ProjectSummary | null | undefined;
  projectId: number | null;
  tamano?: "md";
  className?: string;
}

function textoAria(nombre: string, estado: EstadoMotor, alta: number, media: number, ok: number): string {
  if (estado === "alerta") return `${nombre}: alerta, ${alta} ${alta === 1 ? "alerta" : "alertas"}`;
  if (estado === "aviso") return `${nombre}: aviso, ${media} ${media === 1 ? "aviso" : "avisos"}`;
  if (estado === "sin_datos") return `${nombre}: sin datos`;
  return `${nombre}: correcto, ${ok} ${ok === 1 ? "correcta" : "correctas"}`;
}

export function LucesMonitor({ summary, projectId, className }: LucesMonitorProps) {
  const [abierta, setAbierta] = useState<MonitorType | null>(null);
  const lote = summary?.last_batch ?? null;
  // Retardos del hover: 120 ms para abrir (no abrir al cruzar la fila) y
  // 160 ms para cerrar (tiempo de pasar de la luz al popover).
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null);
  const programar = (fn: () => void, ms: number) => {
    if (temporizador.current) clearTimeout(temporizador.current);
    temporizador.current = setTimeout(fn, ms);
  };
  const ratonEntra = (tipo: MonitorType) => programar(() => setAbierta(tipo), 120);
  const ratonSale = () => programar(() => setAbierta(null), 160);

  return (
    <div className={`flex items-center gap-4 ${className ?? ""}`}>
      {MONITORES.map((tipo) => {
        const abiertas = summary?.alerts_open_by_monitor?.[tipo] ?? null;
        // Cruzadas solo por alertas: sin ninguna evaluación del
        // proyecto la luz queda gris; con alguna, correcto salvo alerta abierta.
        const estado =
          tipo === "cross"
            ? estadoMonitor(summary?.last_evaluation_at ? "ok" : null, abiertas)
            : estadoMonitor(lote?.states_by_monitor?.[tipo] ?? null, abiertas);
        const Icono = ICONO_MONITOR[tipo];
        const checks = lote?.checks_by_state?.[tipo];
        const conCifra = estado === "alerta" || estado === "aviso";
        const cifra = estado === "alerta" ? (abiertas?.alta ?? 0) : (abiertas?.media ?? 0);
        const GlifoCnt = GLIFO_ESTADO[estado];
        const aria = textoAria(ETIQUETA_MONITOR[tipo], estado, abiertas?.alta ?? 0, abiertas?.media ?? 0, checks?.ok ?? 0);
        return (
          <Popover key={tipo} open={abierta === tipo} onOpenChange={(o) => setAbierta(o ? tipo : null)}>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label={aria}
                onMouseEnter={() => ratonEntra(tipo)}
                onMouseLeave={ratonSale}
                onFocus={() => setAbierta(tipo)}
                onClick={(e) => {
                  e.stopPropagation();
                  e.preventDefault();
                  if (temporizador.current) clearTimeout(temporizador.current);
                  setAbierta((actual) => (actual === tipo ? null : tipo));
                }}
                className="relative inline-flex size-9 flex-none items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                style={{
                  background: estado === "sin_datos" ? "var(--state-nodata)" : colorEstado(estado, "relleno"),
                  opacity: estado === "sin_datos" ? 0.85 : 1,
                }}
              >
                <Icono className="size-[18px]" strokeWidth={1.75} style={{ color: "var(--state-on-fill)" }} aria-hidden="true" />
                {conCifra ? (
                  <span
                    className="absolute -top-1.5 -right-2.5 inline-flex h-[17px] items-center justify-center gap-0.5 rounded-full pr-1.5 pl-1 text-[10px] font-bold tabular-nums"
                    style={{ background: "var(--foreground)", color: "var(--background)", boxShadow: "0 0 0 2px var(--card)" }}
                  >
                    <GlifoCnt className="size-2.5" strokeWidth={2.4} aria-hidden="true" />
                    {cifra}
                  </span>
                ) : null}
              </button>
            </PopoverTrigger>
            <DetallePopover
              tipo={tipo}
              estado={estado}
              lote={lote}
              abiertas={abiertas}
              ultimaEvaluacion={summary?.last_evaluation_at}
              projectId={projectId}
              onRatonEntra={() => ratonEntra(tipo)}
              onRatonSale={ratonSale}
            />
          </Popover>
        );
      })}
    </div>
  );
}
