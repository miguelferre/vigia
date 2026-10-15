/**
 * Los cuatro diálogos de `/alertas/:id`: los tres hitos
 * accionables (triaje, investigación, decisión) y "Cerrar con motivo",
 * siempre disponible en cualquier etapa no cerrada. Aparte para que
 * `detalle.tsx` quede por debajo de 9 KB.
 */

import type { ActorBody } from "@/api/types";
import { EJEMPLO_MOTIVO, MotivoDialog } from "@/components/vigia";
import { DialogoInvestigar, DialogoTriaje } from "./HitoDialogos";
import { DialogoDecidir } from "./DialogoDecidir";

export type DialogoAlertaDetalle = "triaje" | "investigacion" | "decision" | "cerrar" | null;

export interface DialogosAlertaDetalleProps {
  alertId: number | null;
  dialogo: DialogoAlertaDetalle;
  onDialogoChange: (dialogo: DialogoAlertaDetalle) => void;
  onConfirmCerrar: (cuerpo: ActorBody) => Promise<void>;
}

export function DialogosAlertaDetalle({ alertId, dialogo, onDialogoChange, onConfirmCerrar }: DialogosAlertaDetalleProps) {
  return (
    <>
      <DialogoTriaje
        alertId={alertId}
        open={dialogo === "triaje"}
        onOpenChange={(open) => onDialogoChange(open ? "triaje" : null)}
      />
      <DialogoInvestigar
        alertId={alertId}
        open={dialogo === "investigacion"}
        onOpenChange={(open) => onDialogoChange(open ? "investigacion" : null)}
      />
      <DialogoDecidir
        alertId={alertId}
        open={dialogo === "decision"}
        onOpenChange={(open) => onDialogoChange(open ? "decision" : null)}
      />
      <MotivoDialog
        open={dialogo === "cerrar"}
        onOpenChange={(open) => onDialogoChange(open ? "cerrar" : null)}
        titulo="Cerrar alerta"
        descripcion="Cerrar es definitivo: la alerta no vuelve a abrirse sola."
        etiquetaConfirmar="Cerrar"
        ejemplo={EJEMPLO_MOTIVO.cerrarAlerta}
        onConfirm={onConfirmCerrar}
      />
    </>
  );
}

export default DialogosAlertaDetalle;
