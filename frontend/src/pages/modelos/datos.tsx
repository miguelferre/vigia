/** Pestaña «Datos» de `/modelos/:id`: datasets, subida y tabla de lotes. */

import { useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { UploadIcon } from "lucide-react";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { useBatches, useDatasets, useProject } from "@/api/queries";
import { useGlosario } from "@/api/queries-contenido";
import type { Dataset } from "@/api/types";
import { DataTable } from "@/components/vigia";
import { Button } from "@/components/ui/button";
import { leerPrecargaSubir } from "@/components/vigia/DemoGuiada/contrato";
import { useCan } from "@/session/session";

import { columnasDataset, columnasLote } from "./datos-columnas";
import SubidaDatasetDialog from "./subida-dataset";

interface Props {
  projectId: number;
}

const LIMITE = 20;

export default function DatosTab({ projectId }: Props) {
  const { data: proyecto } = useProject(projectId);
  const { data: glosario } = useGlosario();
  const [offsetDatasets, setOffsetDatasets] = useState(0);
  const [offsetLotes, setOffsetLotes] = useState(0);
  const { data: datasets, isLoading: cargandoDatasets } = useDatasets(projectId, {
    offset: offsetDatasets,
    limit: LIMITE,
  });
  const { data: lotes, isLoading: cargandoLotes } = useBatches(projectId, {
    offset: offsetLotes,
    limit: LIMITE,
  });
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  // `?demo=subir&guion=&fase=` (contrato.ts): el asistente se abre
  // solo al montar, precargado. Se lee una vez al inicializar el estado.
  const precargaSubir = leerPrecargaSubir(searchParams.toString());
  const [subidaAbierta, setSubidaAbierta] = useState(() => precargaSubir !== null);
  const [continuarDataset, setContinuarDataset] = useState<Dataset | null>(null);
  const puedeMapear = useCan("mapeos");
  const queryClient = useQueryClient();

  const limpiarDemoUrl = () => {
    if (searchParams.has("demo")) {
      const next = new URLSearchParams(searchParams);
      next.delete("demo");
      next.delete("guion");
      next.delete("fase");
      // `setSearchParams` navega a `"?" + params` y pierde el hash (la
      // pestaña activa, #datos/#subir-datos): se conserva navegando a mano.
      const query = next.toString();
      navigate(`${location.pathname}${query ? `?${query}` : ""}${location.hash}`, {
        replace: true,
      });
    }
  };

  const borrarDataset = async (id: number) => {
    try {
      await api.del(`/datasets/${id}?confirm=true`);
      toast.success("Dataset borrado");
      await queryClient.invalidateQueries({ queryKey: ["datasets"] });
    } catch (error) {
      toast.error(mensajeDeError(error));
    }
  };

  const hayEtiquetasLote = (lotes?.items ?? []).some((b) => !!b.phase_label);
  const columnasDatasetTabla = columnasDataset({
    glosario,
    puedeMapear,
    onContinuar: setContinuarDataset,
    onBorrar: borrarDataset,
  });
  const columnasLoteTabla = columnasLote({ proyecto, glosario, hayEtiquetasLote });

  return (
    <div className="flex flex-col gap-8 pt-4">
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Datasets</h2>
          {puedeMapear ? (
            <Button id="subir-datos" className="scroll-mt-20" size="sm" onClick={() => setSubidaAbierta(true)}>
              <UploadIcon className="size-4" aria-hidden="true" />
              Subir dataset
            </Button>
          ) : (
            <span className="text-sm text-muted-foreground">
              Mapear e ingerir datasets requiere un rol con permiso de mapeo.
            </span>
          )}
        </div>
        <DataTable
          data={datasets?.items ?? []}
          columns={columnasDatasetTabla}
          total={datasets?.total}
          offset={offsetDatasets}
          limit={LIMITE}
          onPageChange={setOffsetDatasets}
          cargando={cargandoDatasets}
          titulo="Datasets del proyecto"
        />
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">Lotes</h2>
        <DataTable
          data={lotes?.items ?? []}
          total={lotes?.total}
          offset={offsetLotes}
          limit={LIMITE}
          onPageChange={setOffsetLotes}
          columns={columnasLoteTabla}
          cargando={cargandoLotes}
          titulo="Lotes ingeridos"
        />
      </section>
      <SubidaDatasetDialog
        projectId={projectId}
        open={subidaAbierta}
        onOpenChange={(o) => {
          setSubidaAbierta(o);
          if (!o) limpiarDemoUrl();
        }}
        precargaDemo={precargaSubir}
      />
      <SubidaDatasetDialog
        projectId={projectId}
        open={continuarDataset !== null}
        onOpenChange={(o) => {
          if (!o) setContinuarDataset(null);
        }}
        datasetInicial={continuarDataset}
      />
    </div>
  );
}
