/**
 * Botón principal y diálogos por hito de la alerta: el pie de
 * `AlertaPanel.tsx` y la cabecera de `detalle.tsx` comparten aquí la misma
 * lógica (evitaba una copia en cada uno de los dos, que ya pasaban de 9 KB).
 * «Hacer el triaje» es `MotivoDialog` a secas sobre `POST /alerts/{id}/
 * acknowledge`; «Registrar la investigación» pide los hallazgos, aparte del
 * motivo. «Registrar la decisión» (con el catálogo de acciones) vive en
 * `DialogoDecidir.tsx`, aparte para que este fichero no pasara de 9 KB.
 *
 * Cada diálogo hace su propia mutación (mismo patrón que `acciones.tsx`) e
 * invalida `qk.alert` y `["alerts"]`: así `AlertaPanel.tsx` y `detalle.tsx`
 * solo deciden qué diálogo abrir, con el hito actual que da
 * `useProtocoloHitos` (`protocolo.hitoActual`).
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { qk } from "@/api/queries";
import type { ActorBody, Alert, AlertInvestigateBody, AlertStage } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { EJEMPLO_MOTIVO, MotivoDialog } from "@/components/vigia";
import type { PasoProtocolo } from "./useProtocoloHitos";

type HitoAccionable = "triaje" | "investigacion" | "decision";

/** Etiqueta del botón principal por hito: única fuente para
 * `AlertaPanel.tsx`, `detalle.tsx` y `DialogoDecidir.tsx`. */
export const ETIQUETA_HITO_BOTON: Record<HitoAccionable, string> = {
  triaje: "Hacer el triaje",
  investigacion: "Registrar la investigación",
  decision: "Registrar la decisión",
};

export interface BotonPrincipalAlertaProps {
  /** El hito `current` de `useProtocoloHitos` (`null` sin hito accionable). */
  hitoActual: PasoProtocolo | null;
  stage: AlertStage;
  onAbrir: (hito: HitoAccionable) => void;
}

/**
 * Botón principal de la alerta: el siguiente hito del protocolo, o
 * el texto de la etapa sin hito accionable (decisión ya registrada o alerta
 * cerrada).
 *
 * El hito manda, no el `status` del motor: si la métrica volvió dentro del
 * umbral antes de que nadie mirase la alerta (`status` `en_observacion` por
 * recuperación automática), el triaje sigue pendiente y `acknowledge` lo
 * admite igual (`services/alerting.acknowledge`, que conserva
 * ese `status` y deja el hito en el historial). Antes esa alerta quedaba muda, sin botón.
 */
export function BotonPrincipalAlerta({ hitoActual, stage, onAbrir }: BotonPrincipalAlertaProps) {
  const hito = hitoActual?.key;
  if (hito === "triaje" || hito === "investigacion" || hito === "decision") {
    return (
      <Button type="button" onClick={() => onAbrir(hito)}>
        {ETIQUETA_HITO_BOTON[hito]}
      </Button>
    );
  }
  return (
    <span className="flex items-center text-md font-semibold text-tertiary">
      {stage === "cerrada" ? "Cerrada" : "En seguimiento: el hito 5 avanza con los lotes que llegan"}
    </span>
  );
}

export interface DialogoHitoProps {
  alertId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** «Hacer el triaje» (hito 2): `MotivoDialog` a secas sobre `acknowledge`. */
export function DialogoTriaje({ alertId, open, onOpenChange }: DialogoHitoProps) {
  const queryClient = useQueryClient();

  const mutacion = useMutation({
    mutationFn: (cuerpo: ActorBody) => api.post<Alert>(`/alerts/${alertId}/acknowledge`, cuerpo),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: qk.alert(alertId) }),
        queryClient.invalidateQueries({ queryKey: ["alerts"] }),
      ]);
      toast.success("Triaje hecho: alerta en observación.");
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  return (
    <MotivoDialog
      open={open}
      onOpenChange={onOpenChange}
      titulo={ETIQUETA_HITO_BOTON.triaje}
      etiquetaConfirmar={ETIQUETA_HITO_BOTON.triaje}
      ejemplo={EJEMPLO_MOTIVO.triaje}
      onConfirm={async (cuerpo) => {
        await mutacion.mutateAsync(cuerpo);
      }}
    />
  );
}

/** «Registrar la investigación» (hito 3): hallazgos obligatorios, aparte del motivo. */
export function DialogoInvestigar({ alertId, open, onOpenChange }: DialogoHitoProps) {
  const [hallazgos, setHallazgos] = useState("");
  const queryClient = useQueryClient();

  const mutacion = useMutation({
    mutationFn: (cuerpo: ActorBody) =>
      api.post<Alert>(`/alerts/${alertId}/investigate`, {
        ...cuerpo,
        hallazgos: hallazgos.trim(),
      } satisfies AlertInvestigateBody),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: qk.alert(alertId) }),
        queryClient.invalidateQueries({ queryKey: ["alerts"] }),
      ]);
      toast.success("Investigación registrada.");
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  return (
    <MotivoDialog
      open={open}
      onOpenChange={(o) => {
        if (!o) setHallazgos("");
        onOpenChange(o);
      }}
      titulo={ETIQUETA_HITO_BOTON.investigacion}
      etiquetaConfirmar="Registrar"
      deshabilitado={hallazgos.trim().length === 0}
      ejemplo={EJEMPLO_MOTIVO.investigacion}
      onConfirm={async (cuerpo) => {
        await mutacion.mutateAsync(cuerpo);
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="hito-hallazgos">Hallazgos</Label>
        <Textarea
          id="hito-hallazgos"
          value={hallazgos}
          rows={3}
          placeholder="Qué se ha encontrado al investigar"
          onChange={(e) => setHallazgos(e.target.value)}
        />
      </div>
    </MotivoDialog>
  );
}
