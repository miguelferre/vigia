/**
 * Stepper de nuevo dossier: tres pasos (perfil, experiencia, inventario),
 * campos finales (`system_name`, `domain`, `include_telemetry`) y creación
 * con `MotivoDialog`.
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import type { ActorBody, Dossier } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { MotivoDialog } from "@/components/vigia";
import { useDossierPlantillas, qkAuditoria } from "@/api/queries-auditoria";
import { Formulario } from "./Formulario";
import { PASOS, TITULO_PASO, borradorVacio, construirCuerpo, guardarBorrador, leerBorrador, limpiarBorrador, tieneAlgunaRespuesta } from "./stepper-datos";
import type { BorradorDossier } from "./stepper-datos";

export interface StepperProps {
  projectId: number;
  puedeCrear: boolean;
  onCreado: (dossier: Dossier) => void;
}

export function Stepper({ projectId, puedeCrear, onCreado }: StepperProps) {
  const plantillas = useDossierPlantillas();
  const queryClient = useQueryClient();
  const [paso, setPaso] = useState(0);
  const [borrador, setBorrador] = useState<BorradorDossier>(() => leerBorrador(projectId));
  const [dialogoAbierto, setDialogoAbierto] = useState(false);

  const actualizar = (siguiente: BorradorDossier) => {
    setBorrador(siguiente);
    guardarBorrador(projectId, siguiente);
  };

  const crear = useMutation({
    mutationFn: (cuerpo: ActorBody) =>
      api.post<Dossier>(
        `/projects/${projectId}/dossiers`,
        construirCuerpo(borrador, { actor: cuerpo.actor, role: cuerpo.role ?? "", motivo: cuerpo.motivo }),
      ),
    onSuccess: (dossier) => {
      limpiarBorrador(projectId);
      setBorrador(borradorVacio());
      setPaso(0);
      void queryClient.invalidateQueries({ queryKey: qkAuditoria.lista(projectId) });
      toast.success("Dossier creado.");
      onCreado(dossier);
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  const pasoActual = PASOS[paso];
  const formulario = plantillas.data?.[pasoActual];
  const puedeCrearDossier = tieneAlgunaRespuesta(borrador);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Nuevo dossier ({paso + 1} de {PASOS.length + 1})</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {paso < PASOS.length ? (
          <>
            <h2 className="text-md font-semibold">{TITULO_PASO[pasoActual]}</h2>
            <Formulario
              formulario={formulario}
              respuestas={borrador.respuestas[pasoActual]}
              onChange={(preguntaId, texto) =>
                actualizar({
                  ...borrador,
                  respuestas: { ...borrador.respuestas, [pasoActual]: { ...borrador.respuestas[pasoActual], [preguntaId]: texto } },
                })
              }
            />
          </>
        ) : (
          <div className="flex flex-col gap-4">
            <h2 className="text-md font-semibold">Datos del sistema</h2>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="dossier-system-name">Nombre del sistema</Label>
              <Input
                id="dossier-system-name"
                value={borrador.system_name}
                placeholder="Se toma el nombre del proyecto si se deja en blanco"
                onChange={(e) => actualizar({ ...borrador, system_name: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="dossier-domain">Dominio</Label>
              <Input
                id="dossier-domain"
                value={borrador.domain}
                placeholder="Se toma el dominio del proyecto si se deja en blanco"
                onChange={(e) => actualizar({ ...borrador, domain: e.target.value })}
              />
            </div>
            <div className="flex items-center gap-2.5">
              <Switch
                id="dossier-telemetria"
                checked={borrador.include_telemetry}
                onCheckedChange={(v) => actualizar({ ...borrador, include_telemetry: v })}
              />
              <Label htmlFor="dossier-telemetria">Adjuntar el resumen de deskilling</Label>
            </div>
            {!puedeCrearDossier ? (
              <p className="text-sm text-muted-foreground">
                Rellena al menos una respuesta en alguno de los tres formularios para poder crear el dossier.
              </p>
            ) : null}
          </div>
        )}

        <div className="flex items-center justify-between">
          <Button variant="outline" disabled={paso === 0} onClick={() => setPaso((p) => Math.max(0, p - 1))}>
            Anterior
          </Button>
          {paso < PASOS.length ? (
            <Button onClick={() => setPaso((p) => Math.min(PASOS.length, p + 1))}>Siguiente</Button>
          ) : (
            <Button disabled={!puedeCrear || !puedeCrearDossier} onClick={() => setDialogoAbierto(true)}>
              Crear dossier
            </Button>
          )}
        </div>
      </CardContent>

      <MotivoDialog
        open={dialogoAbierto}
        onOpenChange={setDialogoAbierto}
        titulo="Crear dossier"
        descripcion="Reúne las respuestas de los tres formularios en un dossier de auditoría."
        etiquetaConfirmar="Crear"
        onConfirm={async (cuerpo) => {
          await crear.mutateAsync(cuerpo);
        }}
      />
    </Card>
  );
}
