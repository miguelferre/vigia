/**
 * Vacío del cuadro de mando con proyecto activo pero sin evaluaciones
 * todavía. Distinto de `EmptyDashboard`
 * (sin proyecto activo en absoluto).
 */

import { PlayIcon, UploadIcon } from "lucide-react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/vigia";

export function SinEvaluaciones({ projectId }: { projectId: number }) {
  return (
    <EmptyState
      titulo="Este despliegue todavía no tiene evaluaciones"
      descripcion="Sube un lote de datos para que los monitores empiecen a evaluar, o prueba la plataforma con la demostración guiada."
      accion={
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button asChild>
            <Link to={`/modelos/${projectId}#datos`}>
              <UploadIcon className="size-4" aria-hidden="true" />
              Subir datos
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link to="/demo">
              <PlayIcon className="size-4" aria-hidden="true" />
              Ejecutar la demo
            </Link>
          </Button>
        </div>
      }
    />
  );
}
