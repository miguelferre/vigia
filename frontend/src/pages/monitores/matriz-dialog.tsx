/**
 * Enlace "Ver matriz de confusión" en la cabecera de calidad: abre la
 * matriz completa en un diálogo para no perderla cuando ninguna métrica está
 * ampliada (la sección "Cómo se ha calculado" solo aparece con una ampliada).
 */

import { useState } from "react";
import { TableIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ErrorDeConsulta } from "@/components/vigia";

import { MatrizConfusion } from "@/components/vigia/MatrizConfusion";
import { useEvaluationDetail } from "./usarEvaluacion";

export interface EnlaceMatrizProps {
  evaluationId: number | null;
}

export function EnlaceMatriz({ evaluationId }: EnlaceMatrizProps) {
  const [abierto, setAbierto] = useState(false);
  // Solo se pide el detalle cuando el diálogo se abre: la cabecera no dispara
  // una petición extra en cada carga de la pantalla.
  const detalleQ = useEvaluationDetail(abierto ? evaluationId : null);

  if (evaluationId === null) return null;

  return (
    <>
      <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setAbierto(true)}>
        <TableIcon className="size-4" aria-hidden="true" />
        Ver matriz de confusión
      </Button>
      <Dialog open={abierto} onOpenChange={setAbierto}>
        {/* MN5: ancho al contenido y un único `overflow-x-auto`, el de
            `ui/table.tsx` dentro de `MatrizConfusion` — el de aquí encima
            era el segundo y forzaba scroll horizontal a 1280 px. */}
        <DialogContent className="sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>Matriz de confusión</DialogTitle>
          </DialogHeader>
          {detalleQ.isLoading ? (
            <p className="text-sm text-muted-foreground">Cargando…</p>
          ) : detalleQ.isError || !detalleQ.data ? (
            <ErrorDeConsulta
              que="la evaluación"
              error={detalleQ.error}
              onReintentar={() => void detalleQ.refetch()}
            />
          ) : (
            // `min-w-0`: sin él, la pista de la rejilla del cuerpo del diálogo
            // se ensancha a lo que mide la tabla y es el cuerpo, no la tabla,
            // quien hace scroll (a 375 px el título quedaba fuera de vista).
            <div className="min-w-0">
              <MatrizConfusion evaluacion={detalleQ.data} />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

export default EnlaceMatriz;
