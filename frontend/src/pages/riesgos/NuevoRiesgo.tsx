/**
 * «Nuevo riesgo»: alta manual (sin alerta de origen), botón de la pestaña
 * Registro. Impacto y probabilidad son
 * obligatorios sin `origin_alert_id` (422 del backend si faltan).
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { PlusIcon } from "lucide-react";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import type { ActorBody, Risk, RiskCreateBody } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { EJEMPLO_MOTIVO, MotivoDialog } from "@/components/vigia";
import { ETIQUETA_NIVEL, IMPACTO_LABELS, PROBABILIDAD_LABELS } from "./niveles";
import { NivelResultante } from "./NivelResultante";

export interface NuevoRiesgoProps {
  projectId: number;
  onCreado?: (riesgo: Risk) => void;
}

export function NuevoRiesgo({ projectId, onCreado }: NuevoRiesgoProps) {
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = useState(false);
  const [titulo, setTitulo] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [impacto, setImpacto] = useState<string>("");
  const [probabilidad, setProbabilidad] = useState<string>("");

  const abrir = () => {
    setTitulo("");
    setDescripcion("");
    setImpacto("");
    setProbabilidad("");
    setAbierto(true);
  };

  const alta = useMutation({
    mutationFn: (cuerpo: ActorBody) =>
      api.post<Risk>(`/projects/${projectId}/risks`, {
        ...cuerpo,
        origin_alert_id: null,
        impact_level: Number(impacto),
        probability_level: Number(probabilidad),
        title: titulo.trim(),
        description: descripcion.trim() || null,
      } satisfies RiskCreateBody),
    onSuccess: async (riesgo) => {
      await queryClient.invalidateQueries({ queryKey: ["risks"] });
      toast.success(`${riesgo.code} registrado · ${riesgo.impact_label} × ${riesgo.probability_label} · nivel ${ETIQUETA_NIVEL[riesgo.level]}`);
      onCreado?.(riesgo);
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  const valido = titulo.trim().length > 0 && impacto !== "" && probabilidad !== "";

  return (
    <>
      <Button type="button" size="sm" className="gap-1.5" onClick={abrir}>
        <PlusIcon className="size-4" aria-hidden="true" />
        Nuevo riesgo
      </Button>
      <MotivoDialog
        open={abierto}
        onOpenChange={setAbierto}
        titulo="Nuevo riesgo"
        descripcion="Alta manual, sin alerta de origen: título, impacto y probabilidad son obligatorios."
        etiquetaConfirmar="Registrar"
        ejemplo={EJEMPLO_MOTIVO.nuevoRiesgo}
        deshabilitado={!valido}
        onConfirm={async (cuerpo) => {
          await alta.mutateAsync(cuerpo);
        }}
      >
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="nuevo-riesgo-titulo">Título</Label>
          <Input id="nuevo-riesgo-titulo" value={titulo} onChange={(e) => setTitulo(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="nuevo-riesgo-descripcion">Descripción (opcional)</Label>
          <Textarea
            id="nuevo-riesgo-descripcion"
            rows={2}
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="nuevo-riesgo-impacto">Impacto</Label>
            <Select value={impacto} onValueChange={setImpacto}>
              <SelectTrigger id="nuevo-riesgo-impacto" className="w-full">
                <SelectValue placeholder="Elige impacto" />
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
            <Label htmlFor="nuevo-riesgo-probabilidad">Probabilidad</Label>
            <Select value={probabilidad} onValueChange={setProbabilidad}>
              <SelectTrigger id="nuevo-riesgo-probabilidad" className="w-full">
                <SelectValue placeholder="Elige probabilidad" />
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
        <NivelResultante impacto={impacto} probabilidad={probabilidad} />
      </MotivoDialog>
    </>
  );
}

export default NuevoRiesgo;
