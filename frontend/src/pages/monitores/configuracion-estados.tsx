/**
 * Sección «Estados» de la hoja «Configurar»: explica qué
 * activa cada estado del motor, tras los umbrales y antes de la
 * configuración técnica (donde vive `interval_windows_max`, "editable
 * abajo"). De solo lectura: no configurable, nada se guarda aquí.
 *
 * El glifo y el color de cada fila salen de `StateBadge`
 * (`components/vigia/StateBadge.tsx`), que a su vez los toma de
 * `lib/iconos.ts` (glifo) y de los tokens de `lib/metrics.ts`
 * (`lib/estado-monitor.ts` comparte ese mismo vocabulario de estado).
 */

import { Link } from "react-router";

import { StateBadge } from "@/components/vigia";
import type { EstadoMotor, MonitorType } from "@/api/types";

export interface ConfiguracionEstadosProps {
  monitorType: MonitorType;
  /** `interval_windows_max` en vivo desde la config del formulario (solo lo calcula equidad). */
  ventanasIntervalo: number | null;
}

/** Solo los cuatro estados que hace falta explicar; "correcto" no lo necesita. */
const FILAS: readonly EstadoMotor[] = ["alerta", "aviso", "inestable", "sin_datos"];

function textoInestable(monitorType: MonitorType, ventanas: number | null): string {
  if (monitorType !== "fairness") {
    return "No aplica: solo el monitor de equidad calcula un intervalo por ventana.";
  }
  const n = ventanas ?? "N";
  return `El intervalo de las últimas ${n} ventanas cruza el umbral (N = «Ventanas del intervalo», editable abajo).`;
}

function textoDeEstado(estado: EstadoMotor, monitorType: MonitorType, ventanas: number | null): string {
  switch (estado) {
    case "alerta":
      return "La métrica cruza su umbral: los umbrales de arriba.";
    case "aviso":
      return "Se queda a menos del 10 % del umbral: banda fija de Vigía.";
    case "inestable":
      return textoInestable(monitorType, ventanas);
    case "sin_datos":
      return "Todavía no hay evaluación con la que calcular la métrica.";
    default:
      return "";
  }
}

export function ConfiguracionEstados({ monitorType, ventanasIntervalo }: ConfiguracionEstadosProps) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm text-muted-foreground">Estados</h3>
      <ul className="flex flex-col gap-2">
        {FILAS.map((estado) => (
          <li key={estado} className="flex items-start gap-2.5">
            <StateBadge estado={estado} size="sm" className="mt-0.5 shrink-0" />
            <span className="text-sm text-muted-foreground">
              {textoDeEstado(estado, monitorType, ventanasIntervalo)}
            </span>
          </li>
        ))}
      </ul>
      <Link to="/ayuda#simbolos" className="text-sm text-primary underline-offset-2 hover:underline">
        Ver los símbolos
      </Link>
    </div>
  );
}
