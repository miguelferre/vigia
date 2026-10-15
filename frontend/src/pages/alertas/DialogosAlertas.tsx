/**
 * Los dos `MotivoDialog` de `alertas/index.tsx`: cerrar una
 * alerta individual y la acción en lote (poner en observación o cerrar la
 * selección). Aparte para que ese fichero quede por debajo de 9 KB.
 */

import type { ActorBody, Alert } from "@/api/types";
import { EJEMPLO_MOTIVO, MotivoDialog } from "@/components/vigia";

export interface DialogosAlertasProps {
  cerrarIndividual: Alert | null;
  onCerrarIndividualOpenChange: (open: boolean) => void;
  onConfirmCerrarIndividual: (cuerpo: ActorBody) => Promise<void>;
  accionLote: "acknowledge" | "close" | null;
  onAccionLoteOpenChange: (open: boolean) => void;
  onConfirmAccionLote: (cuerpo: ActorBody) => Promise<void>;
  seleccionSize: number;
}

export function DialogosAlertas({
  cerrarIndividual,
  onCerrarIndividualOpenChange,
  onConfirmCerrarIndividual,
  accionLote,
  onAccionLoteOpenChange,
  onConfirmAccionLote,
  seleccionSize,
}: DialogosAlertasProps) {
  return (
    <>
      <MotivoDialog
        open={cerrarIndividual !== null}
        onOpenChange={onCerrarIndividualOpenChange}
        titulo="Cerrar alerta"
        descripcion="Cerrar es definitivo: la alerta no vuelve a abrirse sola."
        etiquetaConfirmar="Cerrar"
        ejemplo={EJEMPLO_MOTIVO.cerrarAlerta}
        onConfirm={onConfirmCerrarIndividual}
      />
      <MotivoDialog
        open={accionLote !== null}
        onOpenChange={onAccionLoteOpenChange}
        titulo={
          // Concordancia singular/plural ("Cerrar 1 alerta", no "1 alertas").
          accionLote === "close"
            ? `Cerrar ${seleccionSize} ${seleccionSize === 1 ? "alerta" : "alertas"}`
            : `Poner en observación ${seleccionSize} ${seleccionSize === 1 ? "alerta" : "alertas"}`
        }
        descripcion={
          accionLote === "close"
            ? "Cerrar es definitivo: ninguna de las alertas seleccionadas vuelve a abrirse sola."
            : "Registra el reconocimiento humano de las alertas seleccionadas."
        }
        etiquetaConfirmar={accionLote === "close" ? "Cerrar" : "Poner en observación"}
        ejemplo={accionLote === "close" ? EJEMPLO_MOTIVO.cerrarAlerta : EJEMPLO_MOTIVO.observarAlerta}
        onConfirm={onConfirmAccionLote}
      />
    </>
  );
}

export default DialogosAlertas;
