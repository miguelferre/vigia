/**
 * Sección «Plantilla de mapeo» de la pestaña «Configuración»:
 * enseña la plantilla del proyecto y deja editarla con motivo, sobre
 * `PATCH /projects/{id}` con `mapping_template`, que la sustituye entera y
 * deja el evento `proyecto.plantilla_actualizada` con el antes y el después.
 * Vale para las próximas subidas: lo ya ingerido se rehace reiniciando el
 * despliegue («Zona de riesgo») y volviendo a subir los ficheros.
 */

import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/api/client";
import { useDatasets } from "@/api/queries";
import type { ActorBody, ProjectDetail } from "@/api/types";
import { MotivoDialog } from "@/components/vigia";
import { Button } from "@/components/ui/button";
import { PlantillaCampos } from "./configuracion-plantilla-form";
import {
  ID_ZONA_RIESGO,
  aBorrador,
  aPlantilla,
  huellaDePlantilla,
  leerPlantilla,
  type BorradorPlantilla,
} from "./configuracion-plantilla-helpers";
import { textoRangos } from "@/lib/metrics";
import { capacidades, clasesDelProyecto, favorablesComoLista } from "@/lib/tipo-tarea";
import { nombresColumnas } from "./mapeo-dataset-helpers";

interface Props {
  projectId: number;
  proyecto: ProjectDetail | undefined;
}

function irAZonaDeRiesgo() {
  document.getElementById(ID_ZONA_RIESGO)?.scrollIntoView({ behavior: "smooth", block: "center" });
}

export function PlantillaMapeo({ projectId, proyecto }: Props) {
  const queryClient = useQueryClient();
  const { data: datasets } = useDatasets(projectId);
  const plantilla = leerPlantilla(proyecto?.mapping_template_json);
  // En multiclase la plantilla guarda las clases y el conjunto favorable entero.
  const multiclase = proyecto ? capacidades(proyecto.task_type).favorables === "conjunto" : false;
  const clasesProyecto = proyecto ? clasesDelProyecto(proyecto) : [];
  // En regresión la plantilla lleva la unidad y el rango favorable en vez del valor favorable.
  const regresion = proyecto ? capacidades(proyecto.task_type).rangoFavorable : false;
  // Un alta sin plantilla guarda la unidad y el rango en el proyecto; la plantilla nueva parte de ellos.
  const delProyecto = regresion ? { unidad: proyecto?.target_unit ?? null, rangos: proyecto?.favorable_ranges ?? [] } : null;
  const aBorradorDelProyecto = () => aBorrador(plantilla, multiclase, clasesProyecto, regresion, delProyecto);
  const [abierto, setAbierto] = useState(false);
  const [borrador, setBorrador] = useState<BorradorPlantilla>(aBorradorDelProyecto);

  const columnas = useMemo(() => {
    const vistas = new Set<string>();
    for (const d of datasets?.items ?? []) for (const c of nombresColumnas(d)) vistas.add(c);
    return Array.from(vistas);
  }, [datasets]);

  const abrir = () => {
    setBorrador(aBorradorDelProyecto());
    setAbierto(true);
  };

  const guardar = async (cuerpo: ActorBody) => {
    // Un `Error` aquí deja el diálogo abierto con el motivo (MotivoDialog lo enseña).
    const nueva = aPlantilla(borrador, plantilla);
    if (plantilla !== null && huellaDePlantilla(nueva) === huellaDePlantilla(plantilla)) {
      toast.info("No había cambios que guardar");
      return;
    }
    await api.patch(`/projects/${projectId}`, { ...cuerpo, mapping_template: nueva });
    await queryClient.invalidateQueries({ queryKey: ["projects"] });
    toast.success("Plantilla de mapeo actualizada");
  };

  const vista = aBorradorDelProyecto();
  const filas: [string, string][] = [
    ...(regresion
      ? ([
          ["Unidad", vista.unidad],
          [
            "Rango favorable",
            textoRangos(
              vista.rangos
                .filter((r) => r.min !== "" || r.max !== "")
                .map((r): [number | null, number | null] => [r.min === "" ? null : Number(r.min), r.max === "" ? null : Number(r.max)]),
              vista.unidad || null,
            ),
          ],
        ] as [string, string][])
      : multiclase
      ? ([
          ["Clases", vista.clases.join(", ")],
          ["Clases favorables", favorablesComoLista(plantilla?.favorable_label).join(", ")],
        ] as [string, string][])
      : ([["Valor favorable", plantilla?.favorable_label == null ? "" : String(plantilla.favorable_label)]] as [
          string,
          string,
        ][])),
    ["Identificador", plantilla?.id_col ?? ""],
    ["Etiqueta", plantilla?.label_col ?? ""],
    ["Predicción", plantilla?.prediction_col ?? ""],
    ...((regresion
      ? []
      : multiclase
        ? [["Probabilidad por clase", (plantilla?.probability_cols ?? []).join(", ")]]
        : [["Probabilidad", plantilla?.probability_col ?? ""]]) as [string, string][]),
    ["Fecha", plantilla?.timestamp_col ?? ""],
    ["Variables", (plantilla?.feature_cols ?? []).join(", ")],
    ["Atributo protegido", plantilla?.protected_attr_col ?? ""],
    ...(plantilla?.protected_attr_col
      ? ([
          ["Grupo supervisado", vista.unpriv],
          ["Grupo de referencia", vista.priv],
        ] as [string, string][])
      : []),
  ];

  return (
    <section className="flex flex-col gap-3" data-testid="plantilla-mapeo">
      <h2 className="text-sm font-semibold">Plantilla de mapeo</h2>
      <p className="text-xs text-muted-foreground">
        Lo que se hereda en cada subida: columnas del modelo, {regresion ? "unidad y rango favorable" : multiclase ? "clases favorables" : "valor favorable"} y variables. Los
        cambios valen para las próximas subidas; para rehacer lo ya ingerido, reinicia el despliegue
        en{" "}
        <Button type="button" variant="link" className="h-auto p-0 text-xs" onClick={irAZonaDeRiesgo}>
          Zona de riesgo
        </Button>{" "}
        y vuelve a subir los ficheros.
      </p>
      {plantilla === null ? (
        <p className="text-sm text-muted-foreground">
          Este despliegue no tiene plantilla: cada dataset se mapea por separado.
        </p>
      ) : (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
          {filas.map(([nombre, valor]) => (
            <div key={nombre} className="contents">
              <dt className="text-muted-foreground">{nombre}</dt>
              <dd className="break-words">{valor || "Sin fijar"}</dd>
            </div>
          ))}
        </dl>
      )}
      <Button size="sm" variant="outline" className="w-fit" onClick={abrir}>
        {plantilla === null ? "Crear plantilla" : "Editar plantilla"}
      </Button>

      <MotivoDialog
        open={abierto}
        onOpenChange={setAbierto}
        titulo="Plantilla de mapeo"
        etiquetaConfirmar="Guardar plantilla"
        onConfirm={guardar}
      >
        <PlantillaCampos
          borrador={borrador}
          onCambiar={(parcial) => setBorrador((b) => ({ ...b, ...parcial }))}
          columnas={columnas}
        />
      </MotivoDialog>
    </section>
  );
}

export default PlantillaMapeo;
