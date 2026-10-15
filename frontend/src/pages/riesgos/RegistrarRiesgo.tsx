/**
 * «Registrar riesgo» desde una alerta: botón
 * que abre el diálogo de alta con `origin_alert_id`. Montado en
 * `AlertaPanel.tsx` y `alertas/detalle.tsx`; misma firma que su esqueleto.
 *
 * El formulario es `DialogoRegistrarRiesgo`, que también abre `DialogoDecidir`
 * al confirmar una decisión con la acción «Registrar riesgo» marcada.
 *
 * Impacto y probabilidad por defecto son "Propuesta del monitor" (se manda
 * `null` y el backend la calcula por `monitor_type`/`severity` de la
 * alerta, tabla de §6.10); el profesional puede corregirla antes de
 * guardar.
 */

import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldAlertIcon } from "lucide-react";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import type { ActorBody, Alert, Risk, RiskCreateBody } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { EJEMPLO_MOTIVO, MotivoDialog } from "@/components/vigia";
import { useCan } from "@/session/session";
import { ETIQUETA_NIVEL, IMPACTO_LABELS, PROBABILIDAD_LABELS } from "./niveles";
import { NivelResultante } from "./NivelResultante";

export interface BotonRegistrarRiesgoProps {
  alerta: Alert;
  /** Estilo del botón según el sitio: `outline` en el pie, `secondary` en «Más acciones». */
  variant?: "outline" | "secondary";
}

const PROPUESTA = "propuesta";

export interface DialogoRegistrarRiesgoProps {
  alerta: Alert;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DialogoRegistrarRiesgo({ alerta, open: abierto, onOpenChange: setAbierto }: DialogoRegistrarRiesgoProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [titulo, setTitulo] = useState(alerta.title);
  const [descripcion, setDescripcion] = useState("");
  const [impacto, setImpacto] = useState<string>(PROPUESTA);
  const [probabilidad, setProbabilidad] = useState<string>(PROPUESTA);

  // Al abrirse, el formulario vuelve a la propuesta (estado derivado en el render).
  const [abiertoAntes, setAbiertoAntes] = useState(abierto);
  if (abierto !== abiertoAntes) {
    setAbiertoAntes(abierto);
    if (abierto) {
      setTitulo(alerta.title);
      setDescripcion("");
      setImpacto(PROPUESTA);
      setProbabilidad(PROPUESTA);
    }
  }

  const alta = useMutation({
    mutationFn: (cuerpo: ActorBody) =>
      api.post<Risk>(`/projects/${alerta.project_id}/risks`, {
        ...cuerpo,
        origin_alert_id: alerta.id,
        impact_level: impacto === PROPUESTA ? null : Number(impacto),
        probability_level: probabilidad === PROPUESTA ? null : Number(probabilidad),
        title: titulo.trim(),
        description: descripcion.trim() || null,
      } satisfies RiskCreateBody),
    onSuccess: async (riesgo) => {
      await queryClient.invalidateQueries({ queryKey: ["risks"] });
      await queryClient.invalidateQueries({ queryKey: ["alerts"] });
      toast.success(`${riesgo.code} registrado · ${riesgo.impact_label} × ${riesgo.probability_label} · nivel ${ETIQUETA_NIVEL[riesgo.level]}`, {
        action: {
          label: "Ver en Riesgos",
          onClick: () => navigate(`/riesgos?riesgo=${riesgo.id}`),
        },
      });
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  return (
    <MotivoDialog
      open={abierto}
      onOpenChange={setAbierto}
      titulo="Registrar riesgo"
      descripcion="Abre un riesgo en la matriz a partir de esta alerta."
      etiquetaConfirmar="Registrar"
      ejemplo={EJEMPLO_MOTIVO.registrarRiesgo}
      deshabilitado={titulo.trim().length === 0}
      onConfirm={async (cuerpo) => {
        await alta.mutateAsync(cuerpo);
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="riesgo-titulo">Título</Label>
        <Input id="riesgo-titulo" value={titulo} onChange={(e) => setTitulo(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="riesgo-descripcion">Descripción (opcional)</Label>
        <Textarea
          id="riesgo-descripcion"
          rows={2}
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="riesgo-impacto">Impacto</Label>
          <Select value={impacto} onValueChange={setImpacto}>
            <SelectTrigger id="riesgo-impacto" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={PROPUESTA}>Propuesta del monitor</SelectItem>
              {Object.entries(IMPACTO_LABELS).map(([valor, etiqueta]) => (
                <SelectItem key={valor} value={valor}>
                  {etiqueta}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="riesgo-probabilidad">Probabilidad</Label>
          <Select value={probabilidad} onValueChange={setProbabilidad}>
            <SelectTrigger id="riesgo-probabilidad" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={PROPUESTA}>Propuesta del monitor</SelectItem>
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
      <p className="text-xs text-muted-foreground">
        <Link to="/riesgos" className="text-link hover:underline">
          Ver Riesgos
        </Link>
      </p>
    </MotivoDialog>
  );
}

export default function BotonRegistrarRiesgo({ alerta, variant = "outline" }: BotonRegistrarRiesgoProps) {
  const puedeConfig = useCan("config");
  const [abierto, setAbierto] = useState(false);

  // Una alerta retirada (su lote se borró) tampoco se registra como riesgo.
  if (!puedeConfig || alerta.status === "cerrada" || alerta.status === "retirada") return null;

  return (
    <>
      <Button type="button" variant={variant} className="w-fit gap-2" onClick={() => setAbierto(true)}>
        <ShieldAlertIcon className="size-4" aria-hidden="true" />
        Registrar riesgo
      </Button>
      <DialogoRegistrarRiesgo alerta={alerta} open={abierto} onOpenChange={setAbierto} />
    </>
  );
}
