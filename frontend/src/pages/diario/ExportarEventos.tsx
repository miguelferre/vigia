/**
 * Botones de exportación del diario (`GET /events/export`), aparte para que
 * `index.tsx` no supere 9 KB. La exportación respeta los
 * mismos filtros que la tabla: desde, solo este proyecto, carril, tipo de
 * objeto y correlación. El diálogo dice cuáles aplica.
 *
 * Cada botón abre una confirmación con el periodo y el
 * formato; al confirmar se descarga con `fetch` (un fallo sale en español
 * dentro del propio diálogo, nunca como JSON en una pestaña nueva) y, si la
 * descarga fue bien, `POST /events/exportaciones` deja el evento en el diario.
 */

import { useState } from "react";
import { DownloadIcon } from "lucide-react";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/** Los filtros de la pantalla del diario que acotan lo que se exporta. */
export interface FiltrosExportacion {
  sinceIso: string;
  /** Proyecto elegido con «Solo este proyecto», o `null` para todos. */
  projectId: number | null;
  proyectoNombre?: string | null;
  actorKind: string | null;
  objectType: string | null;
  correlationId: string;
}

export interface ExportarEventosProps {
  filtros: FiltrosExportacion;
}

/** «solo este modelo (X), carril user…»: los filtros activos, para decirlos en el diálogo. */
export function textoFiltros(f: FiltrosExportacion): string {
  const partes: string[] = [];
  if (f.projectId !== null) partes.push(f.proyectoNombre ? `solo el modelo «${f.proyectoNombre}»` : "solo este modelo");
  if (f.actorKind) partes.push(`el carril «${f.actorKind}»`);
  if (f.objectType) partes.push(`el tipo de objeto «${f.objectType}»`);
  if (f.correlationId) partes.push(`la correlación «${f.correlationId}»`);
  return partes.join(", ");
}

/** Los filtros del registro de la exportación (el POST ya lleva su propia `correlation_id`). */
function paramsRegistro(f: FiltrosExportacion) {
  return {
    actor_kind: f.actorKind ?? undefined,
    object_type: f.objectType ?? undefined,
    filter_correlation_id: f.correlationId || undefined,
  };
}

function paramsDe(f: FiltrosExportacion) {
  return {
    since: f.sinceIso || undefined,
    project_id: f.projectId ?? undefined,
    actor_kind: f.actorKind ?? undefined,
    object_type: f.objectType ?? undefined,
  };
}

type Formato = "json" | "html";

const NOMBRE_FICHERO: Record<Formato, string> = {
  json: "evidencias-vigia.json",
  html: "evidencias-vigia.html",
};

function textoPeriodo(sinceIso: string): string {
  if (!sinceIso) return "el diario completo, de principio a fin";
  const desde = new Date(sinceIso).toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" });
  return `desde el ${desde} hasta ahora`;
}

export function ExportarEventos({ filtros }: ExportarEventosProps) {
  const sinceIso = filtros.sinceIso;
  const activos = textoFiltros(filtros);
  const [formato, setFormato] = useState<Formato | null>(null);
  const [exportando, setExportando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cerrar = () => {
    setFormato(null);
    setError(null);
  };

  const confirmar = async () => {
    if (!formato) return;
    setExportando(true);
    setError(null);
    try {
      await api.download("/events/export", NOMBRE_FICHERO[formato], {
        params: { format: formato, ...paramsDe(filtros), correlation_id: filtros.correlationId || undefined },
      });
    } catch (e) {
      setError(mensajeDeError(e));
      setExportando(false);
      return;
    }
    try {
      const registro = { format: formato, since: sinceIso || null, project_id: filtros.projectId };
      const params = paramsRegistro(filtros);
      await api.post("/events/exportaciones", registro, { params });
      toast.success(`Diario exportado en ${formato.toUpperCase()}; queda anotado en el diario`);
    } catch (e) {
      toast.warning(`El fichero se ha descargado, pero no se ha podido anotar en el diario: ${mensajeDeError(e)}`);
    }
    setExportando(false);
    cerrar();
  };

  return (
    <div className="flex max-w-full flex-col items-end gap-1">
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setFormato("json")}>
          <DownloadIcon className="size-4" aria-hidden="true" />
          Exportar JSON
        </Button>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setFormato("html")}>
          <DownloadIcon className="size-4" aria-hidden="true" />
          Exportar HTML
        </Button>
      </div>
      {activos ? (
        <p className="max-w-72 text-right text-xs text-muted-foreground" data-testid="aviso-filtros-exportacion">
          La exportación respeta los filtros de la pantalla: {activos}.
        </p>
      ) : null}

      <Dialog open={formato !== null} onOpenChange={(o) => (o ? undefined : cerrar())}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Exportar el diario</DialogTitle>
            <DialogDescription>
              Se descargará {textoPeriodo(sinceIso)}
              {activos ? `, con ${activos}` : ""}, en formato {formato?.toUpperCase()}. La
              exportación queda anotada en el diario, con tu nombre y la hora.
            </DialogDescription>
          </DialogHeader>
          {error ? (
            <p role="alert" className="text-sm text-destructive" data-testid="error-exportar-diario">
              No se ha podido exportar: {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={cerrar}>
              Cancelar
            </Button>
            <Button type="button" onClick={() => void confirmar()} disabled={exportando}>
              {exportando ? "Exportando…" : "Exportar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default ExportarEventos;
