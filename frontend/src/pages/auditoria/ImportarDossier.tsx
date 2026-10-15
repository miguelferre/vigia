/**
 * Importar `dossier.json`: junto al formulario de alta de
 * `/auditoria`. Lee el fichero en el navegador, quita las claves que empiezan
 * por guion bajo (notas del fichero) y lo manda a
 * `POST /projects/{id}/dossiers/import` con actor y motivo. El resultado es un
 * dossier más: se selecciona y se revisa como cualquier otro. Un JSON que no
 * valida vuelve como 422 con el campo que falla, en español.
 */

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import type { ActorBody, Dossier } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MotivoDialog } from "@/components/vigia";
import { qkAuditoria } from "@/api/queries-auditoria";

export interface ImportarDossierProps {
  projectId: number;
  puedeCrear: boolean;
  onCreado: (dossier: Dossier) => void;
}

type Contenido = Record<string, unknown>;

function leerContenido(texto: string): Contenido {
  const datos: unknown = JSON.parse(texto);
  if (datos === null || typeof datos !== "object" || Array.isArray(datos)) {
    throw new Error("El fichero no es un objeto JSON con los campos de un dossier.");
  }
  return Object.fromEntries(Object.entries(datos as Contenido).filter(([clave]) => !clave.startsWith("_")));
}

export function ImportarDossier({ projectId, puedeCrear, onCreado }: ImportarDossierProps) {
  const queryClient = useQueryClient();
  const entrada = useRef<HTMLInputElement>(null);
  const [nombre, setNombre] = useState<string | null>(null);
  const [contenido, setContenido] = useState<Contenido | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialogoAbierto, setDialogoAbierto] = useState(false);

  const importar = useMutation({
    mutationFn: (cuerpo: ActorBody) =>
      api.post<Dossier>(`/projects/${projectId}/dossiers/import`, {
        ...contenido,
        actor: cuerpo.actor,
        role: cuerpo.role ?? "",
        motivo: cuerpo.motivo,
      }),
    onSuccess: (dossier) => {
      void queryClient.invalidateQueries({ queryKey: qkAuditoria.lista(projectId) });
      toast.success("Dossier importado.");
      setNombre(null);
      setContenido(null);
      if (entrada.current) entrada.current.value = "";
      onCreado(dossier);
    },
    onError: (e: unknown) => setError(mensajeDeError(e)),
  });

  const elegirFichero = async (fichero: File | undefined) => {
    setError(null);
    setContenido(null);
    setNombre(fichero?.name ?? null);
    if (!fichero) return;
    try {
      setContenido(leerContenido(await fichero.text()));
    } catch (e) {
      setError(e instanceof SyntaxError ? "El fichero no es un JSON válido." : mensajeDeError(e));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Importar dossier.json</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          Si ya tienes el dossier de otro sistema en el formato de <code className="break-all">interaction_review</code>, súbelo aquí en lugar de
          rellenar los formularios. Queda como un dossier más y se revisa igual.
        </p>
        {/* El control nativo no parece un botón; el input va oculto y el botón secundario lo abre. */}
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={entrada}
            id="dossier-import-fichero"
            type="file"
            accept=".json,application/json"
            className="peer sr-only"
            aria-label="Fichero dossier.json"
            onChange={(e) => void elegirFichero(e.target.files?.[0])}
          />
          <Button type="button" variant="secondary" asChild>
            <label htmlFor="dossier-import-fichero" className="cursor-pointer peer-focus-visible:ring-2 peer-focus-visible:ring-ring">
              Elegir fichero
            </label>
          </Button>
          <span className="text-sm text-muted-foreground [overflow-wrap:anywhere]">{nombre ?? "Ningún fichero elegido"}</span>
        </div>
        {error ? (
          <p role="alert" className="text-sm text-destructive [overflow-wrap:anywhere]">
            {error}
          </p>
        ) : null}
        <div>
          <Button disabled={!puedeCrear || contenido === null || importar.isPending} onClick={() => setDialogoAbierto(true)}>
            Importar{nombre ? ` ${nombre}` : ""}
          </Button>
        </div>
      </CardContent>
      <MotivoDialog
        open={dialogoAbierto}
        onOpenChange={setDialogoAbierto}
        titulo="Importar dossier"
        descripcion="Crea un dossier con el contenido del fichero."
        etiquetaConfirmar="Importar"
        onConfirm={async (cuerpo) => {
          setError(null);
          await importar.mutateAsync(cuerpo);
        }}
      />
    </Card>
  );
}
