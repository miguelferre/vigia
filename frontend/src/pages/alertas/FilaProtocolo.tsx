/**
 * Una fila (marca + tarjeta) del protocolo por hitos, vista completa
 * (incluye la fila informativa sin columna de
 * protocolo). Aparte de `ProtocoloHitos.tsx` para no pasar de 9 KB en ese
 * fichero.
 */

import { Fragment } from "react";

import { Card } from "@/components/ui/card";
import { StateBadge } from "@/components/vigia";
import { formatoFecha } from "@/lib/metrics";
import { cn } from "@/lib/utils";
import { ETIQUETA_HITO_STATUS, ICONO_HITO, MarcaHito } from "./ProtocoloHitos";
import { Info } from "lucide-react";
import type { PasoProtocolo } from "./useProtocoloHitos";
import type { EstadoMotor } from "@/api/types";

const ESTADO_A_MOTOR: Record<PasoProtocolo["status"], EstadoMotor> = {
  done: "ok",
  current: "inestable",
  pending: "sin_datos",
  informativo: "sin_datos",
};

export interface FilaProtocoloProps {
  paso: PasoProtocolo;
  activo: boolean;
  cardRef: (nodo: HTMLDivElement | null) => void;
}

export function FilaProtocolo({ paso, activo, cardRef }: FilaProtocoloProps) {
  // Índice, no llamada: el compilador de React tomaría `iconoHito(...)` por
  // crear un componente en el render. `Info` para un hito extra.
  const Icono = (ICONO_HITO as Record<string, typeof Info>)[paso.key] ?? Info;
  // Sin columna de protocolo (responsable/plazo/hecho por).
  const informativo = paso.status === "informativo";
  return (
    <Fragment>
      <div className="relative z-10 flex items-center justify-center">
        <MarcaHito status={paso.status} />
      </div>
      <Card
        ref={cardRef}
        tabIndex={-1}
        className={cn(
          "grid grid-cols-1 overflow-hidden outline-none",
          informativo
            ? "sm:grid-cols-[minmax(0,5fr)_minmax(0,4fr)]"
            : "sm:grid-cols-[minmax(0,5fr)_minmax(0,4fr)_180px]",
          activo && "ring-2 ring-ring",
        )}
      >
        <div className="flex gap-3 p-3">
          <div className="flex size-9 flex-none items-center justify-center rounded-md bg-muted text-tertiary">
            <Icono className="size-4" strokeWidth={1.5} aria-hidden="true" />
          </div>
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="text-xs font-semibold tracking-[.06em] text-tertiary uppercase">
              Paso {paso.orden}
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-md font-semibold">{paso.titulo}</span>
              <StateBadge estado={ESTADO_A_MOTOR[paso.status]} texto={ETIQUETA_HITO_STATUS[paso.status]} size="sm" />
            </div>
            <span className="text-md text-tertiary">{paso.descripcion}</span>
          </div>
        </div>
        <div className="flex flex-col gap-1.5 border-t border-border p-3 sm:border-t-0 sm:border-l">
          <span className="text-xs font-semibold tracking-[.06em] text-tertiary uppercase">Entregables</span>
          <ul className="flex flex-col gap-1.5">
            {paso.entregables.map((entregable) => (
              <li key={entregable} className="flex items-center gap-1.5 text-md">
                {informativo ? null : <MarcaHito status={paso.status === "done" ? "done" : "pending"} size={14} />}
                <span className={!informativo && paso.status === "done" ? undefined : "text-tertiary"}>
                  {entregable}
                </span>
              </li>
            ))}
          </ul>
        </div>
        {informativo ? null : (
          <div className="flex flex-col gap-1.5 border-t border-border p-3 sm:border-t-0 sm:border-l">
            <span className="text-xs font-semibold tracking-[.06em] text-tertiary uppercase">Protocolo</span>
            <span className="text-md text-tertiary">
              {paso.responsable ? `Responsable: ${paso.responsable}` : "Sin responsable fijado"}
              {paso.plazoDias !== null ? ` · Plazo: ${paso.plazoDias} día${paso.plazoDias === 1 ? "" : "s"}` : ""}
            </span>
            {paso.status === "done" && paso.hechoPor ? (
              <span className="text-md text-tertiary">
                Hecho por {paso.hechoPor}
                {paso.hechoEn ? ` · ${formatoFecha(paso.hechoEn)}` : ""}
              </span>
            ) : null}
          </div>
        )}
      </Card>
    </Fragment>
  );
}

export default FilaProtocolo;
