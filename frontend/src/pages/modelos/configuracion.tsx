/** Pestaña «Configuración» de `/modelos/:id`: PATCH, plantilla de mapeo, reinicio y borrado. */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { useProject } from "@/api/queries";
import type { ActorBody, DeploymentStage } from "@/api/types";
import { ChipDespliegue, MotivoDialog } from "@/components/vigia";
import { ConfiguracionPrivacidadCampos } from "./configuracion-privacidad";
import { ExplicabilidadAutomaticaCampos } from "./configuracion-explicabilidad";
import { DespliegueCampos } from "./configuracion-despliegue";
import { PlantillaMapeo } from "./configuracion-plantilla";
import { ZonaRiesgoDespliegue } from "./configuracion-zona-riesgo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  projectId: number;
  onBorrado: () => void;
}

export default function ConfiguracionTab({ projectId, onBorrado }: Props) {
  const { data: proyecto } = useProject(projectId);
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [storeFeatures, setStoreFeatures] = useState(true);
  const [explainAuto, setExplainAuto] = useState(true);
  const [explainMethod, setExplainMethod] = useState<"permutation" | "shap">("permutation");
  const [deploymentStage, setDeploymentStage] = useState<DeploymentStage>("desarrollo");
  const [patchAbierto, setPatchAbierto] = useState(false);

  const abrirPatch = () => {
    setName(proyecto?.name ?? "");
    setDescription(proyecto?.description ?? "");
    setStoreFeatures(proyecto?.store_features ?? true);
    setExplainAuto(proyecto?.explain_auto ?? true);
    // `explain_method` genera como `string` en el OpenAPI (campo libre en el
    // backend); se estrecha aquí a la unión que usa el formulario.
    setExplainMethod(proyecto?.explain_method === "shap" ? "shap" : "permutation");
    setDeploymentStage(proyecto?.deployment_stage ?? "desarrollo");
    setPatchAbierto(true);
  };

  const guardarPatch = async (cuerpo: ActorBody) => {
    const original = proyecto;
    // «Calibración hasta» se oculta: `calibration_until` no
    // se lee en ningún servicio, así que este
    // formulario ya no la toca; se manda `clear_calibration: false` para no
    // tocar lo que hubiera guardado.
    const vaciarDescripcion = description.trim() === "" && !!original?.description;
    try {
      const respuesta = await api.patch<{
        name: string;
        description: string | null;
        store_features: boolean;
      }>(`/projects/${projectId}`, {
        ...cuerpo,
        name: name.trim() || null,
        description: vaciarDescripcion ? null : description.trim() || null,
        clear_description: vaciarDescripcion,
        clear_calibration: false,
        store_features: storeFeatures,
        explain_auto: explainAuto,
        explain_method: explainMethod,
        deployment_stage: deploymentStage,
      });
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      const cambio =
        !original ||
        respuesta.name !== original.name ||
        (respuesta.description ?? "") !== (original.description ?? "") ||
        respuesta.store_features !== original.store_features ||
        deploymentStage !== original.deployment_stage;
      if (cambio) {
        toast.success("Despliegue actualizado");
      } else {
        toast.info("No había cambios que guardar");
      }
    } catch (error) {
      toast.error(mensajeDeError(error));
    }
  };

  return (
    <div className="flex flex-col gap-6 pt-4">
      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">Datos del despliegue</h2>
          {proyecto ? <ChipDespliegue estado={proyecto.deployment_stage} /> : null}
        </div>
        <Button size="sm" variant="outline" className="w-fit" onClick={abrirPatch}>
          Editar
        </Button>
      </section>

      <PlantillaMapeo projectId={projectId} proyecto={proyecto} />

      <ZonaRiesgoDespliegue projectId={projectId} proyecto={proyecto} onBorrado={onBorrado} />

      <MotivoDialog
        open={patchAbierto}
        onOpenChange={setPatchAbierto}
        titulo="Editar despliegue"
        etiquetaConfirmar="Guardar"
        onConfirm={guardarPatch}
      >
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg-name">Nombre</Label>
            <Input id="cfg-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg-description">Descripción del despliegue</Label>
            <Textarea
              id="cfg-description"
              rows={3}
              placeholder="Qué modelo se usa y para qué existe este despliegue"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Qué modelo se usa y para qué existe este despliegue.
            </p>
          </div>
          {/* «Calibración hasta» oculto: `Project.calibration_until`
              se guarda pero ningún servicio lo lee (modo calibración de las
              alertas cruzadas, capa humana). Vuelve con esa pantalla. */}
          <DespliegueCampos deploymentStage={deploymentStage} setDeploymentStage={setDeploymentStage} />
          <ConfiguracionPrivacidadCampos
            storeFeatures={storeFeatures}
            setStoreFeatures={setStoreFeatures}
          />
          <ExplicabilidadAutomaticaCampos
            projectId={projectId}
            explainAuto={explainAuto}
            setExplainAuto={setExplainAuto}
            explainMethod={explainMethod}
            setExplainMethod={setExplainMethod}
          />
        </div>
      </MotivoDialog>
    </div>
  );
}
