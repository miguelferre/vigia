/**
 * Los dos estados vacíos de `/monitores/:tipo` antes de llegar a pintar el
 * monitor: tipo de ruta desconocido y sin proyecto activo. Partido de
 * `index.tsx` para no superar 9 KB en ese fichero.
 */

import { SearchXIcon } from "lucide-react";

import { PageHeader, EmptyState, SinProyecto } from "@/components/vigia";
import { ETIQUETA_MONITOR } from "@/lib/metrics";
import type { MonitorType } from "@/api/types";

export function MonitorDesconocido({ tipo }: { tipo: string | undefined }) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader titulo="Monitor desconocido" descripcion={`Ruta /monitores/${tipo ?? ""}`} />
      <EmptyState
        icono={SearchXIcon}
        titulo="Monitor desconocido"
        descripcion="Los tipos válidos son equidad, calidad y deriva."
      />
    </div>
  );
}

export function SinProyectoActivo({ monitorType }: { monitorType: MonitorType }) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader titulo={ETIQUETA_MONITOR[monitorType]} />
      <SinProyecto que="sus monitores" />
    </div>
  );
}
