/**
 * Editor «Protocolo de respuesta» de la hoja «Configurar»:
 * los cinco hitos estándar, más los hitos extra que
 * deja añadir, quitar y mover, y las notas libres de siempre
 * (`protocolo_md`). El estado vive en `useProtocoloEditor`, que
 * `configuracion.tsx` invoca y vuelca en el mismo PATCH que el resto de la
 * hoja (un único «Guardar» con motivo): sin guardado propio ni
 * `MotivoDialog` por hito (el motivo de quitar o mover uno extra es el del
 * guardado del protocolo entero). Bloque por hito aparte, en
 * `configuracion-protocolo-hito.tsx`, y las acciones de añadir/quitar/mover
 * en `configuracion-protocolo-acciones.ts`, para no superar 9 KB.
 */

import { useState } from "react";
import { PlusIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MotivoDialog } from "@/components/vigia";
import type { Monitor } from "@/api/types";
import type { components } from "@/api/schema";

import { VistaPreviaProtocolo } from "./configuracion-vista-previa";
import { BloqueHito, esHitoEstandar } from "./configuracion-protocolo-hito";
import { useAccionesProtocolo } from "./configuracion-protocolo-acciones";
import type { HitoProtocoloEdit } from "./tipos";

type MonitorProtocolStepBody = components["schemas"]["MonitorProtocolStepBody"];

function monitorAHitos(monitor: Monitor): HitoProtocoloEdit[] {
  return monitor.protocol.map((h) => ({
    key: h.key,
    titulo: h.titulo,
    descripcion: h.descripcion,
    entregables: h.entregables,
    responsable: h.responsable ?? "",
    plazoDiasTexto: h.plazo_dias === null ? "" : String(h.plazo_dias),
  }));
}

function hitosAProtocolo(hitos: HitoProtocoloEdit[]): MonitorProtocolStepBody[] {
  return hitos.map((h) => {
    const responsable = h.responsable.trim();
    const plazoTexto = h.plazoDiasTexto.trim();
    const plazo = Number(plazoTexto);
    return {
      key: h.key,
      titulo: h.titulo,
      descripcion: h.descripcion,
      entregables: h.entregables,
      responsable: responsable === "" ? null : responsable,
      plazo_dias: plazoTexto === "" || Number.isNaN(plazo) ? null : plazo,
    };
  });
}

export interface ProtocoloEditor {
  protocoloMd: string;
  setProtocoloMd: (texto: string) => void;
  hitos: HitoProtocoloEdit[];
  setHitos: (hitos: HitoProtocoloEdit[]) => void;
  /** Listo para el `MonitorPatch` de `configuracion.tsx`. */
  payload: () => { protocolo_md: string; protocol: MonitorProtocolStepBody[] };
}

/**
 * Estado del editor, con el mismo patrón de reapertura que `configuracion.tsx`
 * (ajuste de estado derivado en el render, no en un efecto): al reabrir la
 * hoja, los campos vuelven a los del monitor.
 */
export function useProtocoloEditor(monitor: Monitor, open: boolean): ProtocoloEditor {
  const [protocoloMd, setProtocoloMd] = useState(monitor.protocolo_md);
  const [hitos, setHitos] = useState<HitoProtocoloEdit[]>(() => monitorAHitos(monitor));

  const [abiertoAntes, setAbiertoAntes] = useState(open);
  if (open !== abiertoAntes) {
    setAbiertoAntes(open);
    if (open) {
      setProtocoloMd(monitor.protocolo_md);
      setHitos(monitorAHitos(monitor));
    }
  }

  return {
    protocoloMd,
    setProtocoloMd,
    hitos,
    setHitos,
    payload: () => ({ protocolo_md: protocoloMd, protocol: hitosAProtocolo(hitos) }),
  };
}

export interface ConfiguracionProtocoloProps {
  editor: ProtocoloEditor;
}

export function ConfiguracionProtocolo({ editor }: ConfiguracionProtocoloProps) {
  const { restableciendo, errorPlantilla, restablecerPlantilla, cambiarHito, añadirHito, quitarHito, moverHito } =
    useAccionesProtocolo(editor);
  // "Restablecer la plantilla" borra los hitos extra del editor sin
  // deshacer posible; con hitos extra de por medio pide motivo antes
  // (patrón `MotivoDialog`: sin mutación propia, la persistencia real es la
  // del "Guardar" de la hoja, pero el motivo deja rastro de la decisión).
  const [confirmarRestablecer, setConfirmarRestablecer] = useState(false);
  const hayHitosExtra = editor.hitos.some((h) => !esHitoEstandar(h.key));

  const pedirRestablecer = () => {
    if (hayHitosExtra) setConfirmarRestablecer(true);
    else restablecerPlantilla();
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="protocolo-monitor" className="text-sm text-muted-foreground">
          Protocolo de respuesta
        </h3>
        <Button type="button" variant="outline" size="sm" disabled={restableciendo} onClick={pedirRestablecer}>
          Restablecer la plantilla
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Restablecer la plantilla trae solo los cinco hitos estándar: borra los hitos extra que hayas añadido.
      </p>
      {errorPlantilla ? (
        <Alert variant="destructive">
          <AlertDescription>{errorPlantilla}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-2">
        {editor.hitos.map((hito, idx) => (
          <BloqueHito
            key={hito.key}
            hito={hito}
            orden={idx + 1}
            onCambiar={(siguiente) => cambiarHito(idx, siguiente)}
            onQuitar={esHitoEstandar(hito.key) ? undefined : () => quitarHito(idx)}
            onSubir={() => moverHito(idx, -1)}
            onBajar={() => moverHito(idx, 1)}
            puedeSubir={idx > 1}
            puedeBajar={idx < editor.hitos.length - 1}
          />
        ))}
        <Button type="button" variant="outline" size="sm" className="self-start" onClick={añadirHito}>
          <PlusIcon className="size-3.5" strokeWidth={1.5} aria-hidden="true" />
          Añadir hito
        </Button>
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm text-muted-foreground">Notas del protocolo</h3>
        <Textarea value={editor.protocoloMd} rows={5} onChange={(e) => editor.setProtocoloMd(e.target.value)} />
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Vista previa</span>
          <div className="rounded-md border border-border bg-muted/40 p-2">
            <VistaPreviaProtocolo texto={editor.protocoloMd} />
          </div>
        </div>
      </div>

      <MotivoDialog
        open={confirmarRestablecer}
        onOpenChange={setConfirmarRestablecer}
        titulo="Restablecer la plantilla"
        descripcion="Borra los hitos extra que hayas añadido y vuelve a los cinco hitos estándar. No se puede deshacer desde aquí."
        etiquetaConfirmar="Restablecer"
        onConfirm={() => restablecerPlantilla()}
      />
    </div>
  );
}
