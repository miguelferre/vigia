/**
 * Las dos alertas de `/monitores/:tipo`: evaluación de
 * `?evaluacion=<id>` no cargada, y periodo personalizado con «Desde»
 * posterior a «Hasta». Partido de `index.tsx` por tamaño al montar el
 * bloque «Distribuciones».
 */

import { TriangleAlertIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";

export function AvisoEvaluacionNoCargada({ id }: { id: number }) {
  return (
    <Alert>
      <TriangleAlertIcon />
      <AlertDescription>La evaluación {id} no está entre las últimas cargadas.</AlertDescription>
    </Alert>
  );
}

export function AvisoPeriodoInvalido() {
  return (
    <Alert variant="destructive">
      <TriangleAlertIcon />
      <AlertDescription>La fecha Desde debe ser anterior a Hasta.</AlertDescription>
    </Alert>
  );
}
