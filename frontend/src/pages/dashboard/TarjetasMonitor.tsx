/**
 * Cuatro tarjetas de monitor del cuadro, siempre visibles:
 * sustituyen a `PestanasMonitores` sin pestañas ni
 * métrica. Datos de `useProjectState` (`worst_state`, `last_evaluated_at`)
 * y de la fila del proyecto en `useProjectsSummary` (`alerts_open_by_monitor`
 * y `last_batch.checks_by_state`, B2): nada de `useAlerts`.
 */

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjectState, useProjectsSummary } from "@/api/queries";
import { useGlosario } from "@/api/queries-contenido";
import { estadoMonitor } from "@/lib/estado-monitor";
import { ETIQUETA_MONITOR } from "@/lib/metrics";
import type { MonitorType } from "@/api/types";
import { TarjetaMonitor } from "./TarjetaMonitor";

/**
 * Texto de reserva mientras `content/glosario.json` no tenga la clave. `checks_by_state["cross"]` cuenta siete comprobaciones
 * (CX-1, CX-2, CX-4 a CX-6 más `human_review_zero`; CX-3
 * aparte, igual que `human_review_zero`, porque ninguna de las dos abre
 * `Alert`). El texto real de `content/glosario.json:comprobaciones_umbral`
 * puede no estar actualizado.
 */
const TEXTO_COMPROBACIONES_RESERVA =
  "Medidas del último lote dentro de umbral; en equidad cada grupo supervisado es una comprobación; cruzadas tiene siete.";

const MONITORES: { clave: MonitorType; ruta: string; textoEnlace: string; textoUltimaEvaluacion: string }[] = [
  { clave: "fairness", ruta: "/monitores/equidad", textoEnlace: "Ver monitor", textoUltimaEvaluacion: "Evaluado" },
  { clave: "quality", ruta: "/monitores/calidad", textoEnlace: "Ver monitor", textoUltimaEvaluacion: "Evaluado" },
  { clave: "drift", ruta: "/monitores/deriva", textoEnlace: "Ver monitor", textoUltimaEvaluacion: "Evaluado" },
  // El detalle de las cruzadas y su
  // calibración viven en `/capa-humana#cruzadas`, no en la tabla genérica.
  { clave: "cross", ruta: "/capa-humana#cruzadas", textoEnlace: "Ver capa humana", textoUltimaEvaluacion: "Comprobado" },
];

export function TarjetasMonitor({ projectId }: { projectId: number | null }) {
  const { data: state, isLoading: cargandoState } = useProjectState(projectId);
  const { data: resumen, isLoading: cargandoResumen } = useProjectsSummary();
  const glosarioQ = useGlosario();
  const textoAyudaCorrectas = glosarioQ.data?.comprobaciones_umbral?.definicion ?? TEXTO_COMPROBACIONES_RESERVA;

  if (cargandoState || cargandoResumen) {
    return (
      <div id="tarjetas" className="grid scroll-mt-20 grid-cols-1 gap-4 @md:grid-cols-2 @5xl:grid-cols-4">
        {MONITORES.map((m) => (
          <Card key={m.clave} className="h-[162px] p-3.5">
            <Skeleton className="h-full w-full" />
          </Card>
        ))}
      </div>
    );
  }

  const summary = resumen?.items.find((p) => p.id === projectId)?.summary;

  return (
    <div id="tarjetas" className="grid scroll-mt-20 grid-cols-1 gap-4 @md:grid-cols-2 @5xl:grid-cols-4">
      {MONITORES.map((m) => {
        const monitor = state?.monitors.find((mm) => mm.type === m.clave);
        const abiertas = summary?.alerts_open_by_monitor[m.clave];
        const estado = estadoMonitor(monitor?.worst_state, abiertas);
        const checks = summary?.last_batch?.checks_by_state[m.clave];
        return (
          <TarjetaMonitor
            key={m.clave}
            nombre={ETIQUETA_MONITOR[m.clave]}
            estado={estado}
            alta={abiertas?.alta ?? 0}
            media={abiertas?.media ?? 0}
            correctas={checks ? checks.ok : "n/d"}
            ultimaEvaluacion={monitor?.last_evaluated_at ?? null}
            textoUltimaEvaluacion={m.textoUltimaEvaluacion}
            ruta={m.ruta}
            textoEnlace={m.textoEnlace}
            textoAyudaCorrectas={textoAyudaCorrectas}
          />
        );
      })}
    </div>
  );
}
