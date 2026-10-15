/**
 * Configuración de un monitor: activar, umbrales, `config`, protocolo.
 * Guardar pasa por `MotivoDialog` y hace `PATCH /monitors/{id}`.
 * La bandera `laboratorio` no se expone.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { MotivoDialog } from "@/components/vigia";
import { Switch } from "@/components/ui/switch";
import { api, mensajeDeError } from "@/api/client";
import { qk, useProject } from "@/api/queries";
import type { ActorBody, JsonObject, Monitor, MonitorPatch } from "@/api/types";
import { ETIQUETA_MONITOR } from "@/lib/metrics";
import { useTipoTarea } from "@/hooks/useTipoTarea";

import { ConfigSimpleEditor, UmbralesEditor } from "./configuracion-campos";
import { calidadSinFabrica } from "./regresion-datos";
import { ConfiguracionAvanzada } from "./configuracion-avanzado";
import { ConfiguracionEstados } from "./configuracion-estados";
import { ConfiguracionProtocolo, useProtocoloEditor } from "./configuracion-protocolo";
import { AVISO_FALTA_NOTA_UMBRAL, useUmbralesEditables } from "./configuracion-umbrales";
import { partirConfig } from "./configuracion-partir";
import { OrigenConjuntoUmbrales } from "./configuracion-umbral-conjunto";
import type { ConfigSimple } from "./tipos";

export interface ConfiguracionMonitorProps {
  monitor: Monitor;
  projectId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ConfiguracionMonitor({ monitor, projectId, open, onOpenChange }: ConfiguracionMonitorProps) {
  const queryClient = useQueryClient();
  const { simple: simpleInicial, avanzado: avanzadoInicial } = partirConfig(monitor.config);

  const [enabled, setEnabled] = useState(monitor.enabled);
  const edicion = useUmbralesEditables(monitor);
  const { umbrales } = edicion;
  const [configSimple, setConfigSimple] = useState<ConfigSimple>(simpleInicial);
  const [avanzadoTexto, setAvanzadoTexto] = useState(
    Object.keys(avanzadoInicial).length > 0 ? JSON.stringify(avanzadoInicial, null, 2) : "",
  );
  const [motivoAbierto, setMotivoAbierto] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  // Protocolo de respuesta: estado y reapertura propios, mismo patrón que abajo.
  const protocolo = useProtocoloEditor(monitor, open);

  const [abiertoAntes, setAbiertoAntes] = useState(open);
  if (open !== abiertoAntes) {
    setAbiertoAntes(open);
    if (open) {
      const partido = partirConfig(monitor.config);
      setEnabled(monitor.enabled);
      edicion.reabrir();
      setConfigSimple(partido.simple);
      setAvanzadoTexto(Object.keys(partido.avanzado).length > 0 ? JSON.stringify(partido.avanzado, null, 2) : "");
      setJsonError(null);
      setApiError(null);
    }
  }

  // Un valor cambiado hace tuyo el umbral y pide su origen y su nota.
  const { caps, tipo, unidad, rangos } = useTipoTarea(projectId);
  const { data: proyecto } = useProject(projectId);
  // La calidad de multiclase y de regresión no evalúa umbrales de fábrica.
  const multiclaseCalidad = calidadSinFabrica(caps, monitor.type);

  const cambiarConfigSimple = (clave: string, valor: string | number | boolean) => {
    setConfigSimple((prev) => ({ ...prev, [clave]: valor }));
  };

  const prepararGuardado = () => {
    setApiError(null);
    if (edicion.faltaNota) {
      setApiError(AVISO_FALTA_NOTA_UMBRAL);
      return;
    }
    if (avanzadoTexto.trim()) {
      try {
        const parseado: unknown = JSON.parse(avanzadoTexto);
        if (typeof parseado !== "object" || parseado === null || Array.isArray(parseado)) {
          throw new Error("debe ser un objeto JSON");
        }
      } catch (e) {
        setJsonError(e instanceof Error ? e.message : "JSON no válido");
        return;
      }
    }
    setJsonError(null);
    setMotivoAbierto(true);
  };

  const guardar = async (cuerpo: ActorBody) => {
    const avanzado = avanzadoTexto.trim() ? (JSON.parse(avanzadoTexto) as JsonObject) : {};
    const payload: MonitorPatch = {
      actor: cuerpo.actor,
      role: cuerpo.role,
      motivo: cuerpo.motivo,
      enabled,
      config: { ...configSimple, ...avanzado },
      thresholds: { thresholds: umbrales },
      ...protocolo.payload(),
      // Bandera no expuesta: siempre su valor por defecto.
      laboratorio: false,
    };
    try {
      await api.patch<{ monitor: Monitor; event_id: number }>(`/monitors/${monitor.id}`, payload);
      await queryClient.invalidateQueries({ queryKey: qk.monitors(projectId) });
      await queryClient.invalidateQueries({ queryKey: qk.monitor(monitor.id) });
      // La propuesta de umbrales del alta trae el «Umbral actual».
      await queryClient.invalidateQueries({ queryKey: qk.thresholdsProposalDe(projectId) });
      toast.success("Configuración del monitor guardada");
      onOpenChange(false);
    } catch (e) {
      setApiError(mensajeDeError(e));
    }
  };

  return (
    <>
      {/* Con la demo guiada desplegada, la hoja se aparta 20 rem del borde
          (`[data-demo-activa]` en `<html>`, AppShell) para no tapar el panel
          de la demo, como la del panel de alerta; el paso «Dónde se
          configura el protocolo» la abre con `#configurar`. */}
      <Sheet modal={false} open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="right"
          className="w-full overflow-y-auto sm:max-w-xl [[data-demo-activa]_&]:lg:right-80"
          // Sin modal (como el panel de alerta): un clic fuera no la cierra,
          // así «Siguiente» del panel de la demo navega sin pisar nada.
          onInteractOutside={(e) => e.preventDefault()}
        >
          <SheetHeader>
            <SheetTitle>Configurar monitor de {ETIQUETA_MONITOR[monitor.type].toLowerCase()}</SheetTitle>
            <SheetDescription>Los cambios quedan en el diario de eventos con actor y motivo.</SheetDescription>
          </SheetHeader>

          <div className="flex flex-col gap-6 px-4 pb-4">
            <div className="flex items-center gap-3">
              <Switch checked={enabled} onCheckedChange={setEnabled} id="monitor-enabled" label="Monitor activado" />
              <Label htmlFor="monitor-enabled">{enabled ? "Activado" : "Desactivado"}</Label>
            </div>

            {edicion.enConjunto ? (
              <OrigenConjuntoUmbrales edicion={edicion} dominio={proyecto?.domain} />
            ) : null}
            <UmbralesEditor
              umbrales={umbrales}
              onCambiar={edicion.cambiar}
              projectId={projectId}
              multiclaseCalidad={multiclaseCalidad}
              tipo={tipo}
              unidad={unidad}
              iniciales={edicion.iniciales}
              dominio={proyecto?.domain}
              conRango={rangos.length > 0}
              onOrigen={edicion.enConjunto ? undefined : edicion.cambiarOrigen}
              onNota={edicion.enConjunto ? undefined : edicion.cambiarNota}
            />
            <ConfiguracionEstados
              monitorType={monitor.type}
              ventanasIntervalo={
                typeof configSimple.interval_windows_max === "number" ? configSimple.interval_windows_max : null
              }
            />
            <ConfigSimpleEditor
              config={configSimple}
              onCambiar={cambiarConfigSimple}
              clavesBloqueadas={
                monitor.type === "fairness"
                  ? {
                      min_records:
                        "Este valor no se cambia desde la interfaz: lo fija la versión activa del modelo.",
                    }
                  : undefined
              }
            />

            {Object.keys(avanzadoInicial).length > 0 ? (
              <ConfiguracionAvanzada texto={avanzadoTexto} onCambiar={setAvanzadoTexto} error={jsonError} />
            ) : null}

            <ConfiguracionProtocolo editor={protocolo} />

            {apiError ? (
              <Alert variant="destructive">
                <AlertDescription>{apiError}</AlertDescription>
              </Alert>
            ) : null}

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancelar
              </Button>
              <Button onClick={prepararGuardado}>Guardar</Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      <MotivoDialog
        open={motivoAbierto}
        onOpenChange={setMotivoAbierto}
        titulo="Guardar configuración del monitor"
        etiquetaConfirmar="Guardar"
        onConfirm={guardar}
      />
    </>
  );
}
