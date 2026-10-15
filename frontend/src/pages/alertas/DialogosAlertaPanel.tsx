/**
 * Los cuatro diálogos de `AlertaPanel.tsx`: cerrar con motivo
 * y los tres hitos accionables (triaje, investigación, decisión). Aparte
 * para que ese fichero quede por debajo de 9 KB.
 */

import type { ActorBody } from "@/api/types";
import { EJEMPLO_MOTIVO, MotivoDialog } from "@/components/vigia";
import { DialogoInvestigar, DialogoTriaje } from "./HitoDialogos";
import { DialogoDecidir } from "./DialogoDecidir";

export interface DialogosAlertaPanelProps {
  alertId: number | null;
  cerrarAbierto: boolean;
  onCerrarAbiertoChange: (open: boolean) => void;
  onConfirmCerrar: (cuerpo: ActorBody) => Promise<void>;
  dialogoHito: "triaje" | "investigacion" | "decision" | null;
  onDialogoHitoChange: (hito: "triaje" | "investigacion" | "decision" | null) => void;
}

export function DialogosAlertaPanel({
  alertId,
  cerrarAbierto,
  onCerrarAbiertoChange,
  onConfirmCerrar,
  dialogoHito,
  onDialogoHitoChange,
}: DialogosAlertaPanelProps) {
  return (
    <>
      <MotivoDialog
        open={cerrarAbierto}
        onOpenChange={onCerrarAbiertoChange}
        titulo="Cerrar alerta"
        descripcion="Cerrar es definitivo: la alerta no vuelve a abrirse sola."
        etiquetaConfirmar="Cerrar"
        ejemplo={EJEMPLO_MOTIVO.cerrarAlerta}
        onConfirm={onConfirmCerrar}
      />
      <DialogoTriaje
        alertId={alertId}
        open={dialogoHito === "triaje"}
        onOpenChange={(open) => onDialogoHitoChange(open ? "triaje" : null)}
      />
      <DialogoInvestigar
        alertId={alertId}
        open={dialogoHito === "investigacion"}
        onOpenChange={(open) => onDialogoHitoChange(open ? "investigacion" : null)}
      />
      <DialogoDecidir
        alertId={alertId}
        open={dialogoHito === "decision"}
        onOpenChange={(open) => onDialogoHitoChange(open ? "decision" : null)}
      />
    </>
  );
}

export default DialogosAlertaPanel;
