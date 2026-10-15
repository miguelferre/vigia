/** Pestaña «Versiones» de `/modelos/:id`: tabla, activar, fijar línea base y crear. */

import { useState } from "react";
import { PlusIcon } from "lucide-react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { useBatches, useProject } from "@/api/queries";
import { useAvisoLineaBase } from "@/api/queries-monitor-proyecto";
import { useGlosario } from "@/api/queries-contenido";
import type { ActorBody, ModelVersion } from "@/api/types";
import { DataTable, MotivoDialog } from "@/components/vigia";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArtefactoSubidaDialog } from "./artefacto-subida";
import { numeroLote } from "@/lib/fases";
import { etiquetaLote } from "./etiquetas";
import { columnasVersiones } from "./versiones-columnas";
import { FijarLineaBaseDialog } from "./versiones-baseline";
import { NuevaVersionDialog } from "./versiones-nueva";
import { PasosVersion } from "./versiones-pasos";
import { TEXTO_UNA_SOLA_VERSION } from "./versiones-textos";

interface Props {
  projectId: number;
}

export default function VersionesTab({ projectId }: Props) {
  const { data: proyecto, isLoading } = useProject(projectId);
  const { data: lotes } = useBatches(projectId);
  const { data: glosario } = useGlosario();
  const avisoLineaBase = useAvisoLineaBase(projectId);
  const queryClient = useQueryClient();

  const [activarId, setActivarId] = useState<number | null>(null);
  const [activarCongelar, setActivarCongelar] = useState("");
  const [baselineVersion, setBaselineVersion] = useState<ModelVersion | null>(null);
  const [artefactoVersion, setArtefactoVersion] = useState<ModelVersion | null>(null);
  const [nuevaAbierta, setNuevaAbierta] = useState(false);
  const navigate = useNavigate();

  const invalidar = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["projects"] }),
      queryClient.invalidateQueries({ queryKey: ["state"] }),
    ]);

  const activar = async (cuerpo: ActorBody) => {
    if (activarId === null) return;
    try {
      await api.post(`/model-versions/${activarId}/activate`, {
        ...cuerpo,
        congelar_linea_base: activarCongelar ? Number(activarCongelar) : null,
      });
      await invalidar();
      toast.success(activarCongelar ? "Versión activada y línea base congelada" : "Versión activada");
    } catch (error) {
      toast.error(mensajeDeError(error));
    }
  };

  const abrirFijarBaseline = (v: ModelVersion) => {
    setBaselineVersion(v);
  };

  const abrirActivar = (v: ModelVersion) => {
    setActivarId(v.id);
    setActivarCongelar("");
  };

  const columnas = columnasVersiones({
    lotes: lotes?.items,
    glosario,
    onActivar: abrirActivar,
    onFijarLineaBase: abrirFijarBaseline,
    onSubirArtefacto: setArtefactoVersion,
  });

  const activa = proyecto?.versions.find((v) => v.is_active);
  // Pasos solo para versiones nuevas sin activar: las anteriores a la activa ya pasaron por ahí.
  const sinActivar = (proyecto?.versions ?? []).filter(
    (v) => !v.is_active && v.id !== null && (!activa || (activa.id !== null && v.id > activa.id)),
  );
  // Corrección: el banner usaba `hayLotes` sobre TODOS los lotes del
  // proyecto, así que con la versión activa sin lotes propios pero otras
  // versiones con lotes ya afirmaba (falso) que la activa "ya tiene lotes,
  // pero ninguno fijado como línea base". El backend ya calcula esto bien
  // (`aviso_linea_base`, GET /projects/{id}): se usa tal cual en vez de
  // recomponer el texto a mano con datos sin filtrar por versión.
  const faltaLineaBase = !!activa && !!avisoLineaBase;
  const lotesDeVersionAActivar = (lotes?.items ?? []).filter((lote) => lote.model_version_id === activarId);

  return (
    <div className="flex flex-col gap-4 pt-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setNuevaAbierta(true)}>
          <PlusIcon className="size-4" aria-hidden="true" />
          Nueva versión
        </Button>
      </div>
      {faltaLineaBase && activa && avisoLineaBase && activa.frozen_at === null ? (
        <Alert>
          <AlertTitle>La deriva no se puede medir hasta fijar la línea base</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {avisoLineaBase.charAt(0).toUpperCase() + avisoLineaBase.slice(1)} (versión activa «{activa.label}»).
            </span>
            <Button size="sm" variant="outline" onClick={() => abrirFijarBaseline(activa)}>
              Fijar línea base
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      <DataTable
        data={proyecto?.versions ?? []}
        columns={columnas}
        cargando={isLoading}
        titulo="Versiones del modelo"
      />
      {proyecto && proyecto.versions.length < 2 ? (
        <p className="text-sm text-muted-foreground">{TEXTO_UNA_SOLA_VERSION}</p>
      ) : null}
      {sinActivar.map((v) => (
        <PasosVersion
          key={v.id}
          version={v}
          acciones={{
            onIrADatos: () => navigate({ hash: "#datos" }),
            onFijarLineaBase: abrirFijarBaseline,
            onSubirArtefacto: setArtefactoVersion,
            onActivar: abrirActivar,
          }}
        />
      ))}

      <MotivoDialog
        open={activarId !== null}
        onOpenChange={(o) => !o && setActivarId(null)}
        titulo="Activar versión"
        etiquetaConfirmar="Activar"
        onConfirm={activar}
      >
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="activar-congelar">Congelar línea base al activar (opcional)</Label>
          <Select value={activarCongelar || "sin-congelar"} onValueChange={(v) => setActivarCongelar(v === "sin-congelar" ? "" : v)}>
            <SelectTrigger id="activar-congelar">
              <SelectValue placeholder="Elige un lote" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="sin-congelar">No congelar ahora</SelectItem>
              {/* Corrección: el backend exige que el lote sea de la versión que se
                  activa (`_resolver_lote_para_congelar`, 422 si no); antes se
                  listaban los lotes de todas las versiones del proyecto. */}
              {lotesDeVersionAActivar.map((lote) => (
                <SelectItem key={lote.id} value={String(lote.id)}>
                  {etiquetaLote(lote.phase_label) ?? `lote ${numeroLote(lote.seq)}`} ({lote.n_rows} filas)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {lotesDeVersionAActivar.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Esta versión todavía no tiene lotes propios que congelar.
            </p>
          ) : activarCongelar ? null : (
            <p className="text-xs text-muted-foreground">
              Si activas sin congelar, la deriva no se evaluará hasta que fijes una línea base.
            </p>
          )}
        </div>
      </MotivoDialog>

      <FijarLineaBaseDialog
        key={baselineVersion?.id ?? "ninguna"}
        version={baselineVersion}
        lotes={lotes?.items ?? []}
        onOpenChange={(o) => !o && setBaselineVersion(null)}
        onHecho={invalidar}
      />

      <NuevaVersionDialog
        open={nuevaAbierta}
        onOpenChange={setNuevaAbierta}
        projectId={projectId}
        onCreada={invalidar}
      />

      <ArtefactoSubidaDialog
        version={artefactoVersion}
        lotes={lotes?.items}
        onOpenChange={(o) => !o && setArtefactoVersion(null)}
      />
    </div>
  );
}
