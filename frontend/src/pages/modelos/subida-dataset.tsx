/**
 * Asistente de subida: subir fichero -> mapear columnas -> ingerir -> progreso.
 * Con `precargaDemo` (`?demo=subir&guion=&fase=`, contrato.ts) el
 * fichero de la línea base del guion se carga solo (tipo combinado, fase
 * línea base), el mapeo sale de `upload_mapping` del guion y el paso de
 * ingesta no ofrece «evaluar al terminar» (lo evalúa el atado de la demo).
 */

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { useProject } from "@/api/queries";
import { useGuiones } from "@/api/queries-demo";
import type { Dataset, DatasetKind, DatasetUpload, IngestBody, Job } from "@/api/types";
import { useJob } from "@/realtime/useJob";
import { useCan } from "@/session/session";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import IngestaDatasetForm from "./ingesta-dataset";
import MapeoDatasetForm from "./mapeo-dataset";
import type { MapeoResultado } from "./mapeo-dataset";
import { type PrecargaSubida, usePrecargaFicheroDemo, useNotificarLoteIngerido } from "./subida-dataset-demo";
import { SubidaPasoFichero } from "./subida-paso-fichero";
import { SubidaProgreso } from "./subida-progreso";
import { DialectoDetectado } from "./subida-dialecto";
import { leerColumnasEjemplo } from "./alta-sniff";
import { filasComoTexto, textoErrorMapeo } from "./subida-errores";
import { tipoPorColumnas } from "./subida-tipo-por-fichero";

type Paso = "subir" | "mapear" | "ingerir" | "progreso";

interface Props {
  projectId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Dataset ya existente a retomar (mapear o ingerir); omitido, arranca en «subir». */
  datasetInicial?: Dataset | null;
  precargaDemo?: PrecargaSubida | null;
}

export default function SubidaDatasetDialog({
  projectId,
  open,
  onOpenChange,
  datasetInicial,
  precargaDemo = null,
}: Props) {
  const puedeMapear = useCan("mapeos");
  const { data: proyecto } = useProject(projectId);
  const { data: guiones } = useGuiones({ enabled: precargaDemo !== null });
  const queryClient = useQueryClient();

  const [paso, setPaso] = useState<Paso>("subir");
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [preview, setPreview] = useState<unknown>(null);
  const [subiendo, setSubiendo] = useState(false);
  // Muestra de filas (navegador + vista previa del servidor) de la
  // que salen los valores de la etiqueta para elegir el favorable, y el
  // texto del 422 del mapeo enseñado en el propio formulario.
  const [filasMuestra, setFilasMuestra] = useState<Record<string, string>[]>([]);
  const [errorMapeo, setErrorMapeo] = useState<string | null>(null);
  // El error de una subida o de una ingesta (p. ej. un lote ilegible)
  // se queda en el propio paso hasta que el usuario lo cierra, cambia de
  // fichero o repite con éxito; un aviso emergente se iba antes de leerlo.
  const [errorPaso, setErrorPaso] = useState<string | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<DatasetKind>("combined");
  const [role, setRole] = useState("production");
  const [name, setName] = useState("");
  const [jobId, setJobId] = useState<number | null>(null);
  const inputFileRef = useRef<HTMLInputElement>(null);
  // #269c: `true` desde que la persona toca el selector «Tipo»; el tipo
  // deducido de las columnas del fichero ya no lo pisa (se rearma al cerrar).
  const tipoManualRef = useRef(false);
  // Id del último dataset ya enriquecido con `GET /datasets/{id}` (plantilla
  // aplicada); evita repetir la petición en cada render mientras el diálogo
  // sigue abierto sobre el mismo dataset.
  const datasetEnriquecidoRef = useRef<number | null>(null);
  // `MapeoDatasetForm` deriva sus campos de `dataset` solo en el montaje
  // (`useState(sugerido?.campo ?? "")`, `mapeo-dataset.tsx`): si el
  // enriquecido llega después de que el formulario ya está montado con el
  // `dataset` sin plantilla, hay que remontarlo con una `key` nueva para que
  // vuelva a leer los valores, en vez de confiar en que reaccione al cambio
  // de prop (no lo hace).
  const [mapeoVersion, setMapeoVersion] = useState(0);

  const job = useJob(jobId);

  useEffect(() => {
    if (paso === "progreso" && job.terminado) {
      void queryClient.invalidateQueries({ queryKey: ["batches"] });
      void queryClient.invalidateQueries({ queryKey: ["datasets"] });
      void queryClient.invalidateQueries({ queryKey: ["state"] });
    }
  }, [paso, job.terminado, queryClient]);

  useNotificarLoteIngerido(paso === "progreso", job, jobId, projectId, role);

  // Al abrir con un dataset ya existente, se sincroniza en el render (no en
  // un efecto) para evitar el doble render de un setState dentro de un
  // useEffect; mismo patrón que `seguido` en realtime/useJob.ts.
  const [datasetSincronizado, setDatasetSincronizado] = useState<number | null>(null);
  if (open && datasetInicial && datasetSincronizado !== datasetInicial.id) {
    setDatasetSincronizado(datasetInicial.id);
    setDataset(datasetInicial);
    setPreview(null);
    setPaso(datasetInicial.status === "subido" && puedeMapear ? "mapear" : "ingerir");
  }
  if (!open && datasetSincronizado !== null) {
    setDatasetSincronizado(null);
    if (datasetEnriquecidoRef.current !== null) datasetEnriquecidoRef.current = null;
  }

  // `datasetInicial` viene de `useDatasets`
  // (`GET /projects/{id}/datasets`), que no aplica la plantilla del proyecto
  // a `suggested_mapping` (mismo hueco de `routers/datasets.py` que `subir()`
  // ya compensa arriba, pero solo para la subida en caliente). Al reabrir
  // para mapear un dataset que quedó «Subido» sin mapear, se repite aquí el
  // mismo refresco con `GET /datasets/{id}` (que sí la aplica), una sola vez
  // por dataset.
  useEffect(() => {
    if (!open || !datasetInicial || datasetInicial.status !== "subido") return;
    if (datasetEnriquecidoRef.current === datasetInicial.id) return;
    datasetEnriquecidoRef.current = datasetInicial.id;
    let cancelado = false;
    api
      .get<Dataset>(`/datasets/${datasetInicial.id}`)
      .then((fresco) => {
        if (!cancelado) {
          setDataset(fresco);
          setMapeoVersion((v) => v + 1);
        }
      })
      .catch(() => {
        // Si falla, se queda con `datasetInicial` (ya sincronizado arriba):
        // el mapeo no hereda la plantilla, pero no es un error nuevo.
      });
    return () => {
      cancelado = true;
    };
  }, [open, datasetInicial]);

  // Carga del fichero de la demo (`GET /demo/scenarios/{guion}/files/{fase}`,
  // subida-dataset-demo.ts): pone el fichero en el input y en el estado.
  // `nombreEsperadoDemo` es el nombre descargado: `SubidaPasoFichero` lo usa
  // para avisar si el usuario lo cambia por otro fichero.
  const nombreEsperadoDemo = usePrecargaFicheroDemo(open, precargaDemo, inputFileRef, (fichero, k, r) => {
    setFile(fichero);
    setKind(k);
    setRole(r);
  });

  const mapeoInicialDemo = precargaDemo
    ? (guiones?.items.find((g) => g.key === precargaDemo.guion)?.upload_mapping ?? null)
    : null;

  const cerrar = () => {
    onOpenChange(false);
    setPaso("subir");
    setDataset(null);
    setPreview(null);
    setFile(null);
    setName("");
    setJobId(null);
    setFilasMuestra([]);
    setErrorMapeo(null);
    setErrorPaso(null);
    // El tipo y la fase no se heredan del lote anterior.
    setKind("combined");
    setRole("production");
    tipoManualRef.current = false;
  };

  const cambiarTipo = (k: DatasetKind) => {
    tipoManualRef.current = true;
    setKind(k);
  };

  const cambiarFichero = (f: File | null) => {
    setFile(f);
    setErrorPaso(null);
    // El tipo de partida sale del fichero, no del lote anterior (la demo fija el suyo).
    if (f && precargaDemo === null) {
      void leerColumnasEjemplo(f)
        .then((s) => {
          const tipo = tipoPorColumnas(s.columnas, proyecto?.mapping_template_json);
          // #269c: se lee la marca al resolverse la lectura, no al elegir el fichero.
          if (tipo && !tipoManualRef.current) setKind(tipo);
        })
        .catch(() => undefined);
    }
  };

  const subir = async () => {
    if (!file) return;
    setSubiendo(true);
    setErrorPaso(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("kind", kind);
      form.append("role", role);
      if (name.trim()) form.append("name", name.trim());
      const resultado = await api.upload<DatasetUpload>(`/projects/${projectId}/datasets/upload`, form);
      // La respuesta de la subida ya trae la sugerencia con la
      // plantilla del proyecto aplicada: sin `GET /datasets/{id}` más.
      setDataset(resultado.dataset);
      setPreview(resultado.preview);
      const sniff = await leerColumnasEjemplo(file).catch(() => null);
      setFilasMuestra([...(sniff?.filas ?? []), ...filasComoTexto(resultado.preview)]);
      setErrorMapeo(null);
      setPaso(puedeMapear ? "mapear" : "ingerir");
      toast.success("Dataset subido");
    } catch (error) {
      setErrorPaso(mensajeDeError(error));
    } finally {
      setSubiendo(false);
    }
  };

  const guardarMapeo = async (r: MapeoResultado) => {
    if (!dataset?.id) return;
    try {
      const actualizado = await api.put<Dataset>(`/datasets/${dataset.id}/mapping`, {
        mapping: r.mapping,
      });
      setDataset(actualizado);
      setErrorMapeo(null);
      setPaso("ingerir");
      toast.success("Mapeo guardado");
    } catch (error) {
      setErrorMapeo(textoErrorMapeo(error));
    }
  };

  const ingerir = async (cuerpo: IngestBody) => {
    if (!dataset?.id) return;
    setErrorPaso(null);
    try {
      const trabajo = await api.post<Job>(`/datasets/${dataset.id}/ingest`, cuerpo);
      if (trabajo.id !== null) setJobId(trabajo.id);
      setPaso("progreso");
    } catch (error) {
      setErrorPaso(mensajeDeError(error));
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : cerrar())}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{datasetInicial ? "Continuar dataset" : "Subir dataset"}</DialogTitle>
          <DialogDescription>
            {datasetInicial
              ? "Retomar el mapeo o la ingesta de un dataset ya subido."
              : "Subir, mapear columnas e ingerir como un nuevo lote."}
          </DialogDescription>
        </DialogHeader>

        {paso === "subir" ? (
          <SubidaPasoFichero
            inputFileRef={inputFileRef}
            onFile={cambiarFichero}
            error={errorPaso}
            onCerrarError={() => setErrorPaso(null)}
            kind={kind}
            onKind={cambiarTipo}
            role={role}
            onRole={setRole}
            name={name}
            onName={setName}
            file={file}
            subiendo={subiendo}
            precargaDemo={precargaDemo !== null}
            nombreEsperadoDemo={nombreEsperadoDemo}
            onSubir={() => void subir()}
          />
        ) : null}

        {paso === "mapear" && dataset ? (
          <>
            <DialectoDetectado dialect={dataset.dialect} />
            <MapeoDatasetForm
              // El tipo de tarea del proyecto también remonta el formulario: sus estados de multiclase se fijan al montar.
              key={`${dataset.id}-${mapeoVersion}-${proyecto?.task_type ?? "sin-proyecto"}`}
              dataset={dataset}
              onGuardar={guardarMapeo}
              mapeoInicial={mapeoInicialDemo}
              project={proyecto}
              filasMuestra={filasMuestra}
              error={errorMapeo}
            />
          </>
        ) : null}

        {paso === "ingerir" && dataset ? (
          <IngestaDatasetForm
            versiones={proyecto?.versions ?? []}
            preview={preview}
            onIngerir={ingerir}
            error={errorPaso}
            onCerrarError={() => setErrorPaso(null)}
            ocultarEvaluar={precargaDemo !== null}
            ocultarEtiqueta={precargaDemo !== null}
            esLineaBase={dataset.role === "baseline"}
          />
        ) : null}

        {paso === "progreso" ? <SubidaProgreso job={job} onCerrar={cerrar} projectId={projectId} /> : null}
      </DialogContent>
    </Dialog>
  );
}
