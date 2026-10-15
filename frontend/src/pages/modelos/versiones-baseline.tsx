/** Diálogo «Fijar línea base» de una versión (partido de `versiones.tsx`). */

import { useState } from "react";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import type { ActorBody, Batch, ModelVersion } from "@/api/types";
import { MotivoDialog } from "@/components/vigia";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { numeroLote } from "@/lib/fases";
import { etiquetaLote } from "./etiquetas";
import { SIN_LOTES_PROPIOS } from "./versiones-textos";

interface Props {
  version: ModelVersion | null;
  lotes: readonly Batch[];
  onOpenChange: (open: boolean) => void;
  /** Tras fijarla: refresca las consultas. */
  onHecho: () => Promise<unknown>;
}

/** Montar con `key={version.id}`: el lote elegido no pasa de una versión a otra. */
export function FijarLineaBaseDialog({ version, lotes, onOpenChange, onHecho }: Props) {
  const [lote, setLote] = useState("");
  const delosPropios = lotes.filter((l) => l.model_version_id === version?.id);

  const fijar = async (cuerpo: ActorBody) => {
    if (version === null || version.id === null || !lote) return;
    try {
      await api.post(`/model-versions/${version.id}/baseline`, {
        ...cuerpo,
        batch_id: Number(lote),
        laboratorio: false,
      });
      await onHecho();
      toast.success("Línea base fijada");
    } catch (error) {
      toast.error(mensajeDeError(error));
    }
  };

  return (
    <MotivoDialog
      open={version !== null}
      onOpenChange={onOpenChange}
      titulo={`Fijar línea base de ${version?.label ?? ""}`}
      etiquetaConfirmar="Fijar"
      deshabilitado={!lote}
      onConfirm={fijar}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="baseline-lote">Lote de línea base</Label>
        <Select value={lote} onValueChange={setLote}>
          <SelectTrigger id="baseline-lote">
            <SelectValue placeholder="Elige un lote" />
          </SelectTrigger>
          <SelectContent>
            {delosPropios.map((l) => (
              <SelectItem key={l.id} value={String(l.id)}>
                {etiquetaLote(l.phase_label) ?? `lote ${numeroLote(l.seq)}`} ({l.n_rows} filas)
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {delosPropios.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            {SIN_LOTES_PROPIOS}
          </p>
        ) : null}
      </div>
    </MotivoDialog>
  );
}
