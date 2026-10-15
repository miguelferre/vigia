/**
 * Bloque «Zona de riesgo» de la pestaña «Configuración»: reiniciar y borrar
 * el despliegue. Aparte de `configuracion.tsx` para no superar los 9 KB de
 * ese fichero, como `configuracion-despliegue.tsx`.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import type { ActorBody, ProjectDetail } from "@/api/types";
import { useSession } from "@/session/session";
import { MotivoDialog } from "@/components/vigia";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ID_ZONA_RIESGO } from "./configuracion-plantilla-helpers";

export interface ZonaRiesgoDespliegueProps {
  projectId: number;
  proyecto: ProjectDetail | undefined;
  onBorrado: () => void;
}

export function ZonaRiesgoDespliegue({ projectId, proyecto, onBorrado }: ZonaRiesgoDespliegueProps) {
  const { setProjectId } = useSession();
  const queryClient = useQueryClient();

  const [resetAbierto, setResetAbierto] = useState(false);
  const [resetConfirma, setResetConfirma] = useState("");
  const [borrarAbierto, setBorrarAbierto] = useState(false);
  const [borrarConfirma, setBorrarConfirma] = useState("");

  const reiniciar = async (cuerpo: ActorBody) => {
    try {
      await api.post(`/projects/${projectId}/reset`, { ...cuerpo, confirm: true });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["projects"] }),
        queryClient.invalidateQueries({ queryKey: ["batches"] }),
        queryClient.invalidateQueries({ queryKey: ["state"] }),
      ]);
      toast.success("Despliegue reiniciado");
      setResetConfirma("");
    } catch (error) {
      toast.error(mensajeDeError(error));
    }
  };

  const borrar = async () => {
    try {
      // DELETE /projects/{id} no exige cuerpo (solo `confirm=true` en la
      // query); el actor de la sesión ya quedó actualizado por MotivoDialog.
      await api.del(`/projects/${projectId}`, undefined, { params: { confirm: true } });
      toast.success("Despliegue borrado");
      setProjectId(null);
      onBorrado();
    } catch (error) {
      toast.error(mensajeDeError(error));
    }
  };

  return (
    <>
      <Alert variant="destructive" id={ID_ZONA_RIESGO}>
        <AlertTitle>Zona de riesgo</AlertTitle>
        <AlertDescription className="flex flex-col gap-3">
          <p>
            Reiniciar borra los ficheros subidos, los lotes, las evaluaciones y las alertas; se mantienen
            el despliegue, sus modelos, la plantilla de mapeo, los monitores y los umbrales. Para
            rehacer el mapeo: edita la plantilla, reinicia y vuelve a subir los ficheros.
          </p>
          <Button size="sm" variant="outline" className="w-fit" onClick={() => setResetAbierto(true)}>
            Reiniciar despliegue
          </Button>
          <p>Borrar el despliegue es irreversible: desaparecen sus modelos, datos y diario asociado.</p>
          <Button size="sm" variant="destructive" className="w-fit" onClick={() => setBorrarAbierto(true)}>
            Borrar despliegue
          </Button>
        </AlertDescription>
      </Alert>

      <MotivoDialog
        open={resetAbierto}
        onOpenChange={(o) => {
          setResetAbierto(o);
          if (!o) setResetConfirma("");
        }}
        titulo="Reiniciar despliegue"
        etiquetaConfirmar="Reiniciar"
        deshabilitado={resetConfirma.trim() !== proyecto?.name}
        onConfirm={reiniciar}
      >
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cfg-reset-confirma">Escribe «{proyecto?.name}» para confirmar</Label>
          <Input
            id="cfg-reset-confirma"
            value={resetConfirma}
            onChange={(e) => setResetConfirma(e.target.value)}
          />
        </div>
      </MotivoDialog>

      <MotivoDialog
        open={borrarAbierto}
        onOpenChange={(o) => {
          setBorrarAbierto(o);
          if (!o) setBorrarConfirma("");
        }}
        titulo="Borrar despliegue"
        etiquetaConfirmar="Borrar"
        deshabilitado={borrarConfirma.trim() !== proyecto?.name}
        onConfirm={() => borrar()}
      >
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cfg-borrar-confirma">
            Escribe «{proyecto?.name}» para confirmar. Esta acción no se puede deshacer.
          </Label>
          <Input
            id="cfg-borrar-confirma"
            value={borrarConfirma}
            onChange={(e) => setBorrarConfirma(e.target.value)}
          />
        </div>
      </MotivoDialog>
    </>
  );
}

export default ZonaRiesgoDespliegue;
