/**
 * Resultado de la subida del registro de uso (partido de `RegistroUso.tsx`):
 * filas guardadas, comprobación de codificación en lenguaje llano
 * y los avisos de la respuesta (filas de fechas sin lote).
 * La comprobación nunca rechaza la subida: `posible_inversion` e
 * `inconcluso` son avisos que se enseñan tal cual.
 */

import { TriangleAlertIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { ComprobacionCodificacion, UsageLogUploadResponse } from "@/api/types";
import { ANCLA_CODIFICACION, EnlaceFormato } from "@/pages/modelos/subida-enlace-formato";
import { AYUDA_INCONCLUSO } from "./registro-uso-ayuda";

const PORCENTAJE = new Intl.NumberFormat("es-ES", { style: "percent", maximumFractionDigits: 1 });

function pct(valor: number | null | undefined): string {
  return valor === null || valor === undefined ? "sin dato" : PORCENTAJE.format(valor);
}

function fraseComprobacion(c: ComprobacionCodificacion): { texto: string; tono: "ok" | "aviso" | "neutro" } {
  if (c.estado === "coherente") {
    return { texto: "Las decisiones del modelo en el registro casan con sus predicciones.", tono: "ok" };
  }
  if (c.estado === "posible_inversion") {
    return {
      texto: "Parece que el registro usa la codificación al revés: revisa la opción elegida.",
      tono: "aviso",
    };
  }
  const motivo = (c.motivo ?? "sin más detalle").trim().replace(/\.$/, "");
  return { texto: `No se puede comprobar: ${motivo}.`, tono: "neutro" };
}

const CLASE_TONO = {
  ok: "border-border bg-muted/40",
  aviso: "border-destructive/50 bg-destructive/5",
  neutro: "border-border bg-muted/40",
} as const;

export interface ResultadoSubida {
  respuesta: UsageLogUploadResponse;
  version: string;
  nombre: string;
}

/**
 * `sinCodificacion`: la comprobación de la codificación compara el 0/1 favorable del registro con
 * el de producción. En multiclase y en regresión no hay codificación
 * que revisar, así que no se dibuja.
 */
export function ResultadoRegistro({ resultado, sinCodificacion = false }: { resultado: ResultadoSubida; sinCodificacion?: boolean }) {
  const comprobacion = sinCodificacion ? null : (resultado.respuesta.comprobacion_codificacion ?? null);
  const frase = comprobacion ? fraseComprobacion(comprobacion) : null;
  const avisos = (resultado.respuesta.avisos ?? []).filter((a) => a.trim() !== "");
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3" data-testid="registro-uso-resultado">
      <p className="text-sm">
        <span className="font-semibold">{resultado.respuesta.n_rows}</span> filas guardadas de{" "}
        <span className="font-mono text-xs [overflow-wrap:anywhere]">{resultado.nombre}</span> en la versión{" "}
        <span className="font-semibold">{resultado.version}</span>.
      </p>
      {frase && comprobacion ? (
        <div className={`flex flex-col gap-1 rounded-md border p-2 ${CLASE_TONO[frase.tono]}`}>
          <p className="text-sm font-medium" data-testid="registro-uso-comprobacion">
            {frase.texto}
          </p>
          {frase.tono === "neutro" ? (
            <p className="text-xs text-muted-foreground">
              {AYUDA_INCONCLUSO} <EnlaceFormato texto="Cómo se codifica" ancla={ANCLA_CODIFICACION} className="text-xs" />
            </p>
          ) : null}
          {comprobacion.r !== null && comprobacion.p !== null ? (
            <p className="text-xs text-muted-foreground">
              Decisiones favorables del modelo: {pct(comprobacion.r)} en el registro frente a {pct(comprobacion.p)} en
              producción (n = {comprobacion.n}).
            </p>
          ) : null}
        </div>
      ) : null}
      {avisos.length > 0 ? (
        <Alert data-testid="registro-uso-avisos">
          <TriangleAlertIcon style={{ color: "var(--state-warn)" }} aria-hidden="true" />
          <AlertTitle>{avisos.length === 1 ? "Un aviso de la subida" : `${avisos.length} avisos de la subida`}</AlertTitle>
          <AlertDescription>
            {avisos.map((aviso, i) => (
              <p key={i} className="[overflow-wrap:anywhere]">
                {aviso}
              </p>
            ))}
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
