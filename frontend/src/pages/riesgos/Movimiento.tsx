/**
 * «Movimiento · N días»:
 * `GET /projects/{id}/risks/movements?days=`, dentro de la pestaña Matriz,
 * bajo la matriz. El `texto` viene compuesto del backend (nunca se
 * recompone); el icono por `kind` y el sentido de la flecha en "celda" se
 * derivan de ese texto, no de los valores crudos.
 */

import { useState } from "react";
import { ArrowDownIcon, ArrowRightIcon, ArrowUpIcon, CircleXIcon, PlusCircleIcon } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { useProjectRiskMovements } from "@/api/queries-riesgos";
import type { RiskMovementKind } from "@/api/types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { formatoFechaLarga, formatoRelativo } from "@/lib/fechas";
import { sentidoDeTexto } from "./niveles";

export interface MovimientoProps {
  projectId: number;
}

const ICONO_KIND: Record<RiskMovementKind, LucideIcon> = {
  alta: PlusCircleIcon,
  celda: ArrowRightIcon,
  estado: ArrowRightIcon,
  cierre: CircleXIcon,
};

function iconoDeFila(kind: RiskMovementKind, texto: string): LucideIcon {
  const sentido = sentidoDeTexto(kind, texto);
  if (sentido === "subio") return ArrowUpIcon;
  if (sentido === "bajo") return ArrowDownIcon;
  return ICONO_KIND[kind];
}

export function Movimiento({ projectId }: MovimientoProps) {
  const [dias, setDias] = useState(7);
  const movimientos = useProjectRiskMovements(projectId, dias);

  return (
    <div id="movimiento" className="flex scroll-mt-20 flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-md font-semibold">Movimiento · {dias} días</h2>
        <Select value={String(dias)} onValueChange={(v) => setDias(Number(v))}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">7 días</SelectItem>
            <SelectItem value="30">30 días</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {movimientos.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : (movimientos.data?.items.length ?? 0) === 0 ? (
        <p className="text-sm text-muted-foreground">Sin movimientos en esta ventana.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {movimientos.data?.items.map((m) => {
            const Icono = iconoDeFila(m.kind, m.texto);
            return (
              <li key={m.id} className="flex items-start gap-2 rounded-md border border-border p-2.5 text-sm">
                <Icono className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <div className="flex flex-col gap-0.5">
                  <p>{m.texto}</p>
                  <p className="text-xs text-muted-foreground" title={formatoFechaLarga(m.created_at)}>
                    {m.actor} · {formatoRelativo(m.created_at)}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
