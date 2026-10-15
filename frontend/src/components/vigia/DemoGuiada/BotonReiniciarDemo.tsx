/**
 * «Reiniciar» la demo guiada: `MotivoDialog` (actor y motivo, como toda
 * mutación con `ActorBody`), `POST /demo/runs/{id}/reset` si hay
 * reproducción, borrado del estado y vuelta a `/demo`. Lo usan el panel
 * acoplado y la tarjeta «Demo en curso» de `/demo`.
 */

import { useState } from "react";
import { RefreshCwIcon } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { MotivoDialog } from "@/components/vigia/MotivoDialog";

import { useDemoGuiada } from "./contexto";

export interface BotonReiniciarDemoProps {
  variant?: "ghost" | "outline";
  size?: "sm" | "icon";
  className?: string;
}

export function BotonReiniciarDemo({ variant = "outline", size = "sm", className }: BotonReiniciarDemoProps) {
  const { reiniciar, runId } = useDemoGuiada();
  const [abierto, setAbierto] = useState(false);
  return (
    <>
      <Button
        type="button"
        variant={variant}
        size={size}
        className={className}
        aria-label={size === "icon" ? "Reiniciar la demo" : undefined}
        title="Reiniciar la demo"
        onClick={() => setAbierto(true)}
      >
        <RefreshCwIcon className="size-4" aria-hidden="true" />
        {size === "icon" ? null : "Reiniciar"}
      </Button>
      <MotivoDialog
        open={abierto}
        onOpenChange={setAbierto}
        titulo="Reiniciar la demo"
        descripcion={
          runId !== null
            ? "Borra lo reproducido del caso Digestivo (lotes, evaluaciones, alertas y diario de uso) y deja el proyecto listo para empezar de cero. No se puede deshacer."
            : "Olvida el progreso de la demo y vuelve a la presentación. El modelo creado se conserva."
        }
        etiquetaConfirmar="Reiniciar"
        onConfirm={async (cuerpo) => {
          await reiniciar(cuerpo);
          toast.success("Demo reiniciada");
        }}
      />
    </>
  );
}
