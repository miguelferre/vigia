/**
 * Pie de `AlertaPanel.tsx`: catálogo de acciones
 * plegado (con el registro de riesgo) y el botón principal del
 * hito, con el enlace al monitor. Aparte para que ese fichero quede por
 * debajo de 9 KB.
 */

import { lazy, Suspense } from "react";
import { Link } from "react-router";

import type { AlertDetail } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ETIQUETA_MONITOR } from "@/lib/metrics";
import { Acciones } from "./acciones";
import { BotonPrincipalAlerta } from "./HitoDialogos";
import type { PasoProtocolo } from "./useProtocoloHitos";

// Alta de un riesgo desde la alerta, con impacto y probabilidad
// propuestos por monitor y severidad; el diálogo vive en `pages/riesgos`.
const BotonRegistrarRiesgo = lazy(() => import("@/pages/riesgos/RegistrarRiesgo"));

export interface PieAlertaPanelProps {
  alerta: AlertDetail;
  alertId: number | null;
  hitoActual: PasoProtocolo | null;
  rutaMonitor: string | undefined;
  onCerrarConMotivo: () => void;
  onAbrirDialogoHito: (hito: "triaje" | "investigacion" | "decision") => void;
}

export function PieAlertaPanel({
  alerta: a,
  alertId,
  hitoActual,
  rutaMonitor,
  onCerrarConMotivo,
  onAbrirDialogoHito,
}: PieAlertaPanelProps) {
  if (a.status === "retirada") {
    // Sin acciones sobre una retirada (el backend da 409); solo el enlace.
    return rutaMonitor ? (
      <div className="mt-auto flex items-center gap-2 border-t border-border pt-3">
        <Button asChild type="button" variant="outline">
          <Link to={`/monitores/${rutaMonitor}`}>Ver en {ETIQUETA_MONITOR[a.monitor_type]}</Link>
        </Button>
      </div>
    ) : null;
  }
  return (
    <>
      {/* Catálogo completo de acciones: sigue accesible desde el
          panel y desde "⋯" de la tabla, que abre este mismo panel
          Plegado para no
          competir con el pie. */}
      <details className="text-md">
        <summary className="cursor-pointer font-semibold text-tertiary select-none">Más acciones</summary>
        <div className="mt-2 flex flex-col gap-3">
          {a.status !== "cerrada" ? (
            <Button type="button" variant="outline" className="w-fit" onClick={onCerrarConMotivo}>
              Cerrar con motivo
            </Button>
          ) : null}
          <Suspense fallback={null}>
            <BotonRegistrarRiesgo alerta={a} variant="outline" />
          </Suspense>
          <Acciones alertId={a.id ?? alertId ?? -1} acciones={a.actions} />
        </div>
      </details>

      <div className="sticky bottom-0 mt-auto flex items-center gap-2 border-t border-border bg-card pt-3">
        <BotonPrincipalAlerta hitoActual={hitoActual} stage={a.stage} onAbrir={onAbrirDialogoHito} />
        {rutaMonitor ? (
          <Button asChild type="button" variant="outline">
            <Link to={`/monitores/${rutaMonitor}`}>Ver en {ETIQUETA_MONITOR[a.monitor_type]}</Link>
          </Button>
        ) : null}
      </div>
    </>
  );
}

export default PieAlertaPanel;
