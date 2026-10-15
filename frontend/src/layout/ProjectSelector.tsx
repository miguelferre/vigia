/** Selector de proyecto activo de la cabecera. Persiste en la sesión. */

import { useEffect, useMemo } from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { MENSAJE_RED_CAIDA } from "@/api/client";
import { useProjects } from "@/api/queries";
import { useSession } from "@/session/session";

export function ProjectSelector() {
  const { projectId, setProjectId } = useSession();
  const { data, isPending, isError } = useProjects({ limit: 200 });
  const proyectos = useMemo(() => data?.items ?? [], [data]);

  // Si no hay proyecto elegido, o el guardado ya no existe, se toma el primero.
  useEffect(() => {
    if (proyectos.length === 0) return;
    const existe = proyectos.some((p) => p.id === projectId);
    if (!existe) setProjectId(proyectos[0].id ?? null);
  }, [proyectos, projectId, setProjectId]);

  if (isPending) return <Skeleton className="h-9 w-52" data-loading="true" />;
  if (isError) {
    // Texto corto para la cabecera; el aviso entero está en el cuerpo de la pantalla.
    return (
      <span className="text-sm text-muted-foreground" title={MENSAJE_RED_CAIDA}>
        Sin conexión con Vigía
      </span>
    );
  }
  if (proyectos.length === 0) {
    return <span className="text-sm text-muted-foreground">Sin modelos</span>;
  }

  const activo = proyectos.find((p) => p.id === projectId);
  return (
    <Select
      value={projectId === null ? undefined : String(projectId)}
      onValueChange={(v) => setProjectId(Number(v))}
    >
      <SelectTrigger className="w-52" aria-label="Modelo activo">
        {/* E4-01: el nombre largo se recorta con puntos suspensivos y se lee entero en `title`. */}
        <SelectValue placeholder="Elige un modelo">
          {activo ? (
            <span className="min-w-0 truncate" title={activo.name}>
              {activo.name}
            </span>
          ) : null}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {proyectos.map((p) => (
          <SelectItem key={p.id} value={String(p.id)} title={p.name}>
            {p.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
