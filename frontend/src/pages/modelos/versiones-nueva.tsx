/**
 * Diálogo «Nueva versión de modelo» (partido de
 * `versiones.tsx`): etiqueta, tipo de modelo como selector con su ayuda y
 * ventana de equidad explicada.
 */

import { useState } from "react";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import type { ActorBody } from "@/api/types";
import { MotivoDialog } from "@/components/vigia";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  AYUDA_ETIQUETA_VERSION,
  AYUDA_VENTANA_EQUIDAD,
  TIPOS_DE_MODELO,
} from "./versiones-textos";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: number;
  /** Se llama tras crear la versión, para refrescar las consultas. */
  onCreada: () => Promise<unknown>;
}

export function NuevaVersionDialog({ open, onOpenChange, projectId, onCreada }: Props) {
  const [label, setLabel] = useState("");
  const [modelKind, setModelKind] = useState<string>("external_files");
  const [fairnessWindow, setFairnessWindow] = useState("200");
  const ayudaTipo = TIPOS_DE_MODELO.find((t) => t.valor === modelKind)?.ayuda;

  const crear = async (cuerpo: ActorBody) => {
    try {
      await api.post(`/projects/${projectId}/versions`, {
        ...cuerpo,
        label: label.trim(),
        model_kind: modelKind,
        fairness_window_n: fairnessWindow ? Number(fairnessWindow) : null,
      });
      await onCreada();
      toast.success("Versión creada: sigue sus pasos para activarla");
      setLabel("");
    } catch (error) {
      toast.error(mensajeDeError(error));
    }
  };

  return (
    <MotivoDialog
      open={open}
      onOpenChange={onOpenChange}
      titulo="Nueva versión de modelo"
      etiquetaConfirmar="Crear"
      deshabilitado={!label.trim()}
      onConfirm={crear}
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="v-label">Etiqueta</Label>
          <Input id="v-label" value={label} onChange={(e) => setLabel(e.target.value)} />
          <p className="text-xs text-muted-foreground">{AYUDA_ETIQUETA_VERSION}</p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="v-kind">Tipo de modelo</Label>
          <Select value={modelKind} onValueChange={setModelKind}>
            <SelectTrigger id="v-kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIPOS_DE_MODELO.map((t) => (
                <SelectItem key={t.valor} value={t.valor}>
                  {t.etiqueta}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">{ayudaTipo}</p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="v-window">Ventana de equidad (registros)</Label>
          <Input
            id="v-window"
            type="number"
            value={fairnessWindow}
            onChange={(e) => setFairnessWindow(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{AYUDA_VENTANA_EQUIDAD}</p>
        </div>
      </div>
    </MotivoDialog>
  );
}
