/**
 * Leyenda de estados del panel de la demo guiada: bajo el dato de
 * todo paso que declare un estado esperado, un `details` con los cinco chips
 * del motor (`StateBadge`, mismos tokens que el resto de la aplicación) y una
 * línea por cada uno, más los enlaces a los símbolos de la ayuda y a los
 * monitores del modelo, donde se configuran los umbrales. Se abre sola en el
 * primer paso del guion cuyo dato esperado es «alerta» (quien decide es el
 * panel, con `primerPasoConEstado`) y plegada en el resto; el `key` por paso
 * en el panel hace que cada paso arranque con su valor por defecto.
 */

import { Link } from "react-router";

import type { EstadoMotor } from "@/api/types";
import { StateBadge } from "@/components/vigia/StateBadge";

const LINEA_ESTADO: ReadonlyArray<[EstadoMotor, string]> = [
  ["ok", "dentro del umbral"],
  ["aviso", "cerca del umbral"],
  ["alerta", "fuera del umbral"],
  ["inestable", "la muestra es pequeña"],
  ["sin_datos", "sin evaluación todavía"],
];

export interface LeyendaEstadosProps {
  /** Abierta al montar (solo en el primer paso con alerta). */
  abierta: boolean;
  projectId: number | null;
}

export function LeyendaEstados({ abierta, projectId }: LeyendaEstadosProps) {
  const rutaMonitores = projectId !== null ? `/modelos/${projectId}#monitores` : "/modelos";
  return (
    <details
      open={abierta}
      className="group rounded-lg border border-border bg-background px-3 py-2 text-left"
      data-leyenda-estados={abierta ? "abierta" : "plegada"}
    >
      <summary className="cursor-pointer list-none text-xs font-semibold text-tertiary select-none">
        <span className="mr-1 inline-block transition-transform group-open:rotate-90 motion-reduce:transition-none" aria-hidden="true">
          ›
        </span>
        Qué significan los estados
      </summary>
      <ul className="mt-2 flex flex-col gap-1.5">
        {LINEA_ESTADO.map(([estado, linea]) => (
          <li key={estado} className="flex items-center gap-2 text-xs text-muted-foreground">
            <StateBadge estado={estado} size="sm" />
            <span>{linea}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
        <Link to="/ayuda#simbolos" className="text-primary underline-offset-2 hover:underline">
          Ver símbolos
        </Link>
        <Link to={rutaMonitores} className="text-primary underline-offset-2 hover:underline">
          Configurar umbrales
        </Link>
      </p>
    </details>
  );
}
