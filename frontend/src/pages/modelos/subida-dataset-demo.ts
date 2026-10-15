/**
 * Lógica de la subida precargada desde la demo guiada (`?demo=subir`,
 * contrato.ts), separada de `subida-dataset.tsx` para no superar
 * 9 KB: descarga del fichero enlatado de la fase y el aviso a
 * `notificarDemo` cuando el lote termina de ingerirse.
 */

import { type RefObject, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { API_BASE, ApiError, MENSAJE_RED_CAIDA, mensajeDeError } from "@/api/client";
import type { DatasetKind, JobStatus } from "@/api/types";
import { notificarDemo } from "@/components/vigia/DemoGuiada/contrato";

export interface PrecargaSubida {
  guion: string;
  fase: string;
}

/** Nombre de `Content-Disposition: attachment; filename="…"`, o el de reserva. */
function nombreDeDisposicion(disposicion: string | null): string {
  const coincide = disposicion ? /filename="?([^";]+)"?/.exec(disposicion) : null;
  return coincide?.[1] ?? "caso-digestivo-linea-base.csv";
}

/**
 * Descarga `GET /demo/scenarios/{guion}/files/{fase}` y la pone en el
 * `<input type="file">` (vía `DataTransfer`) y en `onFichero`. Depende de una
 * petición de red: no puede resolverse en el render.
 *
 * Devuelve el nombre del fichero descargado: quien lo llama lo
 * compara con el que haya en el input para avisar si el usuario lo cambió
 * por otro, ya que la demo espera justo ese fichero en esa fase.
 */
export function usePrecargaFicheroDemo(
  open: boolean,
  precargaDemo: PrecargaSubida | null,
  inputFileRef: RefObject<HTMLInputElement | null>,
  onFichero: (fichero: File, kind: DatasetKind, role: string) => void,
): string | null {
  const clave = precargaDemo ? `${precargaDemo.guion}|${precargaDemo.fase}` : null;
  const [aplicada, setAplicada] = useState<string | null>(null);
  const [nombreEsperado, setNombreEsperado] = useState<string | null>(null);

  // Al cerrar el diálogo se olvida lo aplicado, en el render (no en un
  // efecto, patrón del repo): si se reabre con el mismo guion y fase, el
  // fichero se recarga en vez de quedarse en blanco.
  const [abiertoAntes, setAbiertoAntes] = useState(open);
  if (open !== abiertoAntes) {
    setAbiertoAntes(open);
    if (!open && aplicada !== null) {
      setAplicada(null);
      setNombreEsperado(null);
    }
  }

  useEffect(() => {
    if (!open || !precargaDemo || !clave || aplicada === clave) return;
    let cancelado = false;
    (async () => {
      try {
        // Fallo de red: el mismo mensaje común que `api`, no el «Failed to fetch» del navegador.
        const resp = await fetch(
          `${API_BASE}/demo/scenarios/${encodeURIComponent(precargaDemo.guion)}/files/${encodeURIComponent(precargaDemo.fase)}`,
        ).catch(() => {
          throw new ApiError(0, MENSAJE_RED_CAIDA);
        });
        if (!resp.ok) throw new Error("No se ha podido cargar el fichero de la demo");
        const nombre = nombreDeDisposicion(resp.headers.get("content-disposition"));
        const blob = await resp.blob();
        if (cancelado) return;
        const fichero = new File([blob], nombre, { type: "text/csv" });
        if (inputFileRef.current) {
          const dt = new DataTransfer();
          dt.items.add(fichero);
          inputFileRef.current.files = dt.files;
        }
        onFichero(fichero, "combined", "baseline");
        setAplicada(clave);
        setNombreEsperado(nombre);
      } catch (error) {
        toast.error(mensajeDeError(error));
      }
    })();
    return () => {
      cancelado = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onFichero es estable por render, no hace falta re-suscribir por identidad.
  }, [open, precargaDemo, clave, aplicada, inputFileRef]);

  return nombreEsperado;
}

interface JobParaNotificar {
  terminado: boolean;
  status: JobStatus | null;
  result: unknown;
}

/**
 * Avisa a la demo con `lote-ingerido` cuando el trabajo de ingesta termina
 * con éxito; también si el diálogo se cierra justo después (el efecto ya ha
 * corrido antes de que `cerrar()` limpie el estado).
 */
export function useNotificarLoteIngerido(
  enProgreso: boolean,
  job: JobParaNotificar,
  jobId: number | null,
  projectId: number,
  role: string,
): void {
  const notificadoRef = useRef<number | null>(null);
  useEffect(() => {
    if (!enProgreso || !job.terminado || job.status !== "terminado") return;
    if (jobId === null || notificadoRef.current === jobId) return;
    notificadoRef.current = jobId;
    const resultado = job.result as { batch_id?: number | null } | null;
    notificarDemo({ tipo: "lote-ingerido", projectId, batchId: resultado?.batch_id ?? null, role });
  }, [enProgreso, job.terminado, job.status, job.result, jobId, projectId, role]);
}
