/**
 * Anotación humana del diario, en la cabecera junto a «Exportar» (era un
 * botón redondo sobre la línea de tiempo hasta que se retiró).
 * Escribe en `POST /events`: el motivo de `MotivoDialog`
 * es el texto de la anotación y el evento cae en el carril humano con la
 * acción `anotacion.manual`; el SSE del diario lo pinta sin recargar. Con
 * `?demo=anotar&texto=T` (contrato.ts) el diálogo se abre solo con
 * ese texto precargado.
 */

import { useState } from "react";
import { useSearchParams } from "react-router";
import { PlusIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { MotivoDialog } from "@/components/vigia/MotivoDialog";
import { EJEMPLO_MOTIVO } from "@/components/vigia/motivo-textos";
import { api } from "@/api/client";
import type { ActorBody, Event } from "@/api/types";
import { leerPrecargaAnotar, notificarDemo } from "@/components/vigia/DemoGuiada/contrato";

export interface AnotacionHumanaProps {
  projectId: number | null;
  /** La lista vuelve a la primera página, donde entra la anotación. */
  onRegistrada?: (evento: Event) => void;
}

export function AnotacionHumana({ projectId, onRegistrada }: AnotacionHumanaProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const textoPrecarga = leerPrecargaAnotar(searchParams.toString());
  const [abierto, setAbierto] = useState(() => textoPrecarga !== null);

  const limpiarDemoUrl = () => {
    if (searchParams.has("demo")) {
      const next = new URLSearchParams(searchParams);
      next.delete("demo");
      next.delete("texto");
      setSearchParams(next, { replace: true });
    }
  };

  const confirmar = async (cuerpo: ActorBody) => {
    const evento = await api.post<Event>("/events", { ...cuerpo, project_id: projectId });
    onRegistrada?.(evento);
    // Sin demo activa, avisar no tiene efecto (contrato.ts).
    notificarDemo({ tipo: "anotacion-creada", projectId });
  };

  return (
    <>
      <Button
        id="anotar"
        type="button"
        variant="outline"
        size="sm"
        className="scroll-mt-20 gap-2"
        onClick={() => setAbierto(true)}
        title="Añadir anotación humana"
      >
        <PlusIcon className="size-4" strokeWidth={1.5} aria-hidden="true" />
        Anotar
      </Button>
      <MotivoDialog
        open={abierto}
        onOpenChange={(o) => {
          setAbierto(o);
          if (!o) limpiarDemoUrl();
        }}
        titulo="Anotación humana"
        descripcion="Deja constancia de algo que has observado, para que quede en el carril Usuario del diario."
        etiquetaConfirmar="Registrar"
        motivoInicial={textoPrecarga ?? ""}
        ejemplo={EJEMPLO_MOTIVO.anotar}
        onConfirm={confirmar}
      />
    </>
  );
}
