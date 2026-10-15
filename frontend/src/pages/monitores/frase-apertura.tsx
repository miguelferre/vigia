/**
 * Frase de apertura de una pantalla de monitor.
 *
 * `content/` no trae todavía una entrada por monitor
 * (`glosario.json` solo cubre estados, grupos, ventana, muestra mínima,
 * valor frágil y orden manipulado; ver `src/vigia/content/glosario.json`).
 * Se busca la clave `monitor_<tipo>` por si se añade más adelante y, si no
 * está, se degrada a `DESCRIPCION_MONITOR` de `lib/metrics.ts` (que NO se
 * borra: lo sigue usando el cuadro de mando).
 *
 * MN4: el botón "Glosario" y el `GlosarioSheet` que llevaba este
 * fichero se mudan a `cabecera.tsx`, a la fila de acciones, con el mismo
 * sitio fijo en los tres monitores (aquí "salía movido" porque este texto
 * mide muy distinto entre equidad, calidad y deriva).
 */

import { useGlosario } from "@/api/queries-contenido";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { DESCRIPCION_MONITOR } from "@/lib/metrics";
import type { MonitorType } from "@/api/types";

export interface FraseAperturaMonitorProps {
  monitorType: MonitorType;
  /** Proyecto del monitor: en regresión, calidad y equidad hablan de error y de rango favorable. */
  projectId?: number | null;
}

/** Frases de regresión: el glosario del backend habla de aciertos de clase. */
const FRASE_REGRESION: Partial<Record<MonitorType, string>> = {
  quality:
    "Mide cuánto se aleja la predicción del valor real, cuando ese valor llega. Responde a si el modelo sigue siendo tan bueno como el día que se aprobó.",
  fairness:
    "Compara el error del modelo en el grupo supervisado con el del grupo de referencia. Responde a si el modelo se equivoca más con un grupo de personas, y cuánto.",
};

/** Texto de una entrada del glosario, tolerante al nombre de campo real (ver GlosarioSheet.tsx). */
function textoEntrada(entrada: { descripcion?: string; definicion?: string }): string | undefined {
  return entrada.definicion ?? entrada.descripcion;
}

export function FraseAperturaMonitor({ monitorType, projectId }: FraseAperturaMonitorProps) {
  const glosarioQ = useGlosario();
  const { caps } = useTipoTarea(projectId);
  const entrada = glosarioQ.data?.[`monitor_${monitorType}`];
  const frase =
    (caps?.metricas === "regresion" ? FRASE_REGRESION[monitorType] : undefined) ??
    (entrada && textoEntrada(entrada)) ??
    DESCRIPCION_MONITOR[monitorType];

  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm text-muted-foreground">{frase}</p>
    </div>
  );
}
