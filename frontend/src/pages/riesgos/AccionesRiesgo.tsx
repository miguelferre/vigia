/**
 * Acciones de un riesgo (mover, poner en seguimiento, cerrar): botones y
 * sus tres `MotivoDialog`, extraído de `PanelRiesgo.tsx` para que ese
 * fichero se quede por debajo de 9 KB.
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import type { ActorBody, Risk, RiskCloseBody, RiskMoveBody, RiskStatusBody } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { EJEMPLO_MOTIVO, MotivoDialog } from "@/components/vigia";
import { IMPACTO_LABELS, PROBABILIDAD_LABELS } from "./niveles";

export interface AccionesRiesgoProps {
  riesgo: Risk;
}

export function AccionesRiesgo({ riesgo }: AccionesRiesgoProps) {
  const queryClient = useQueryClient();
  const invalidar = async () => {
    await queryClient.invalidateQueries({ queryKey: ["risks"] });
  };

  const [moverAbierto, setMoverAbierto] = useState(false);
  const [impactoNuevo, setImpactoNuevo] = useState<string>("");
  const [probabilidadNueva, setProbabilidadNueva] = useState<string>("");
  const [seguimientoAbierto, setSeguimientoAbierto] = useState(false);
  const [cerrarAbierto, setCerrarAbierto] = useState(false);

  const mover = useMutation({
    mutationFn: (cuerpo: ActorBody) =>
      api.patch<Risk>(`/risks/${riesgo.id}/move`, {
        ...cuerpo,
        impact_level: Number(impactoNuevo),
        probability_level: Number(probabilidadNueva),
      } satisfies RiskMoveBody),
    onSuccess: async () => {
      await invalidar();
      toast.success("Riesgo movido de celda.");
      setMoverAbierto(false);
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  const enSeguimiento = useMutation({
    mutationFn: (cuerpo: ActorBody) =>
      api.patch<Risk>(`/risks/${riesgo.id}/status`, {
        ...cuerpo,
        status: "en_seguimiento",
      } satisfies RiskStatusBody),
    onSuccess: async () => {
      await invalidar();
      toast.success("Riesgo puesto en seguimiento.");
      setSeguimientoAbierto(false);
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  const cerrar = useMutation({
    mutationFn: (cuerpo: ActorBody) => api.post<Risk>(`/risks/${riesgo.id}/close`, cuerpo satisfies RiskCloseBody),
    onSuccess: async () => {
      await invalidar();
      toast.success("Riesgo cerrado.");
      setCerrarAbierto(false);
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  const abrirMover = () => {
    setImpactoNuevo(String(riesgo.impact_level));
    setProbabilidadNueva(String(riesgo.probability_level));
    setMoverAbierto(true);
  };

  if (riesgo.status === "cerrado") return null;

  return (
    <>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={abrirMover}>
          Mover
        </Button>
        {riesgo.status === "abierto" ? (
          <Button type="button" variant="outline" size="sm" onClick={() => setSeguimientoAbierto(true)}>
            Poner en seguimiento
          </Button>
        ) : null}
        <Button type="button" variant="outline" size="sm" onClick={() => setCerrarAbierto(true)}>
          Cerrar
        </Button>
      </div>

      <MotivoDialog
        open={moverAbierto}
        onOpenChange={setMoverAbierto}
        titulo="Mover riesgo"
        descripcion="Cambia la celda del riesgo en la matriz."
        etiquetaConfirmar="Mover"
        ejemplo={EJEMPLO_MOTIVO.moverRiesgo}
        deshabilitado={impactoNuevo === "" || probabilidadNueva === ""}
        onConfirm={async (cuerpo) => {
          await mover.mutateAsync(cuerpo);
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="mover-impacto" className="text-sm font-medium">
              Impacto
            </label>
            <Select value={impactoNuevo} onValueChange={setImpactoNuevo}>
              <SelectTrigger id="mover-impacto" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(IMPACTO_LABELS).map(([valor, etiqueta]) => (
                  <SelectItem key={valor} value={valor}>
                    {etiqueta}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="mover-probabilidad" className="text-sm font-medium">
              Probabilidad
            </label>
            <Select value={probabilidadNueva} onValueChange={setProbabilidadNueva}>
              <SelectTrigger id="mover-probabilidad" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(PROBABILIDAD_LABELS).map(([valor, etiqueta]) => (
                  <SelectItem key={valor} value={valor}>
                    {etiqueta}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </MotivoDialog>

      <MotivoDialog
        open={seguimientoAbierto}
        onOpenChange={setSeguimientoAbierto}
        titulo="Poner en seguimiento"
        descripcion="El riesgo pasa de abierto a en seguimiento."
        etiquetaConfirmar="Poner en seguimiento"
        ejemplo={EJEMPLO_MOTIVO.seguimientoRiesgo}
        onConfirm={async (cuerpo) => {
          await enSeguimiento.mutateAsync(cuerpo);
        }}
      />

      <MotivoDialog
        open={cerrarAbierto}
        onOpenChange={setCerrarAbierto}
        titulo="Cerrar riesgo"
        descripcion="Cerrar es definitivo: el riesgo no vuelve a abrirse (v1)."
        etiquetaConfirmar="Cerrar"
        ejemplo={EJEMPLO_MOTIVO.cerrarRiesgo}
        onConfirm={async (cuerpo) => {
          await cerrar.mutateAsync(cuerpo);
        }}
      />
    </>
  );
}
