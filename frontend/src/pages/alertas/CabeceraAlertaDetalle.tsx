/**
 * Descripción y acciones de la cabecera de `/alertas/:id`: chips, severidad, etapa, métrica y progreso del protocolo a la
 * izquierda de `PageHeader`; botón principal del hito, "Cerrar con motivo" y
 * el registro de riesgo a la derecha. Aparte para que `detalle.tsx` quede
 * por debajo de 9 KB.
 */

import { lazy, Suspense } from "react";

import type { AlertDetail, Batch } from "@/api/types";
import { Button } from "@/components/ui/button";
import { MetricLabel, StateBadge } from "@/components/vigia";
import { useFormatoMetrica } from "@/components/vigia/useFormatoMetrica";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { formatoFecha } from "@/lib/metrics";
import { AvisoRetirada, ChipsCabecera } from "./AlertaPanelCabecera";
import { estadoDeSeveridad, etiquetaSeveridad } from "./severidad";
import { etiquetaEtapa } from "./etapa";
import { BotonPrincipalAlerta } from "./HitoDialogos";
import type { PasoProtocolo, ResultadoProtocoloHitos } from "./useProtocoloHitos";

// Alta de un riesgo desde la ficha, mismo botón que el panel.
const BotonRegistrarRiesgo = lazy(() => import("@/pages/riesgos/RegistrarRiesgo"));

export interface DescripcionAlertaDetalleProps {
  alerta: AlertDetail;
  lote: Batch | null | undefined;
  protocolo: ResultadoProtocoloHitos;
}

export function DescripcionAlertaDetalle({ alerta: a, lote, protocolo }: DescripcionAlertaDetalleProps) {
  const { formato } = useFormatoMetrica(a.project_id);
  const { rangos } = useTipoTarea(a.project_id);
  return (
    <div className="flex flex-col gap-2">
      {/* El chip «Solo lectura» de aquí sugería que toda la ficha (con
          botones operables al lado: triaje, cerrar, registrar riesgo) era de
          solo lectura; lo que es de solo lectura es el texto libre del
          protocolo, que ya lo dice en su propio bloque (`protocolo.tsx`). */}
      <div className="flex flex-wrap items-center gap-1.5">
        <ChipsCabecera alerta={a} lote={lote} />
      </div>
      <div className="flex flex-wrap items-center gap-3 text-md">
        <StateBadge estado={estadoDeSeveridad(a.severity)} texto={etiquetaSeveridad(a.severity)} />
        <span>{etiquetaEtapa(a)}</span>
        <MetricLabel metrica={a.metric_key} grupo={a.group_code} conRango={rangos.length > 0} />
        <span>Último valor: {formato(a.metric_key, a.last_value)}</span>
        <span>Abierta el {formatoFecha(a.opened_at)}</span>
        {!protocolo.cargando ? (
          <span>
            Protocolo: {protocolo.hechos} de {protocolo.total} pasos completados
          </span>
        ) : null}
      </div>
      <AvisoRetirada alerta={a} />
    </div>
  );
}

export interface AccionesAlertaDetalleProps {
  alerta: AlertDetail;
  hitoActual: PasoProtocolo | null;
  onAbrirDialogoHito: (hito: "triaje" | "investigacion" | "decision") => void;
  onCerrarConMotivo: () => void;
}

export function AccionesAlertaDetalle({ alerta: a, hitoActual, onAbrirDialogoHito, onCerrarConMotivo }: AccionesAlertaDetalleProps) {
  // Una alerta retirada no ofrece acciones (el backend da 409).
  if (a.status === "retirada") return null;
  return (
    <>
      {/* El botón principal es siempre el siguiente hito del
          protocolo; "Cerrar con motivo" queda aparte, disponible en
          cualquier etapa no cerrada (mismo componente que el pie del
          panel, `AlertaPanel.tsx`: ver `HitoDialogos.tsx`). */}
      <BotonPrincipalAlerta hitoActual={hitoActual} stage={a.stage} onAbrir={onAbrirDialogoHito} />
      <Button type="button" variant="outline" disabled={a.status === "cerrada"} onClick={onCerrarConMotivo}>
        Cerrar con motivo
      </Button>
      <Suspense fallback={null}>
        <BotonRegistrarRiesgo alerta={a} variant="outline" />
      </Suspense>
    </>
  );
}
