/**
 * Formulario de mapeo de columnas para un dataset recién subido.
 * Compacto: un único rango por grupo cuando `protected_kind` es numérico.
 * Los campos (`mapeo-campos.tsx`) están partidos en fichero propio para
 * quedar por debajo de 9 KB. Vigía no detecta columnas identificadoras ni
 * exige decisiones de privacidad: sin paso de privacidad.
 */

import { useState } from "react";

import type { ProtectedKind } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";

import { capacidades } from "@/lib/tipo-tarea";
import { valoresDistintos } from "./alta-sniff";
import { AvisoSinProbabilidad } from "./aviso-sin-probabilidad";
import { valorDeClase } from "./clases-multiclase";
import MapeoCampos from "./mapeo-campos";
import { useMapeoMulticlase } from "./mapeo-dataset-multiclase";
import type { MapeoDatasetProps, MapeoResultado } from "./mapeo-dataset-tipos";
import {
  categoricosATexto,
  huellaPlantilla,
  nombresColumnas,
  primerRango,
  rangoNumerico,
  soloIdYEtiqueta,
  textoACategoricos,
  valorFavorable,
} from "./mapeo-dataset-helpers";

export type { MapeoResultado };

export default function MapeoDatasetForm({
  dataset,
  onGuardar,
  guardando = false,
  mapeoInicial,
  project,
  filasMuestra = [],
  error = null,
}: MapeoDatasetProps) {
  const columnas = nombresColumnas(dataset);
  // Un dataset `feedback` no pide predicción: `id_col` es
  // obligatorio en `combined`/`payload` salvo que el proyecto no acepte
  // feedback (sin proyecto a mano, la posición más exigente).
  const esFeedback = dataset.kind === "feedback";
  const sugerido = soloIdYEtiqueta(mapeoInicial ?? dataset.suggested_mapping, esFeedback);
  const idColObligatorio = !esFeedback && project?.acepta_feedback !== false;

  const [predictionCol, setPredictionCol] = useState(sugerido?.prediction_col ?? "");
  const [probabilityCol, setProbabilityCol] = useState(sugerido?.probability_col ?? "");
  const [labelCol, setLabelCol] = useState(sugerido?.label_col ?? "");
  const [idCol, setIdCol] = useState(sugerido?.id_col ?? "");
  const [timestampCol, setTimestampCol] = useState(sugerido?.timestamp_col ?? "");
  const [protectedCol, setProtectedCol] = useState(sugerido?.protected_attr_col ?? "");
  const [protectedKind, setProtectedKind] = useState<ProtectedKind>(
    sugerido?.protected_kind ?? "numeric_ranges",
  );
  const rangoUnprivInicial = primerRango(sugerido?.unpriv_groups);
  const rangoPrivInicial = primerRango(sugerido?.priv_groups);
  const [unprivMin, setUnprivMin] = useState(rangoUnprivInicial[0]);
  const [unprivMax, setUnprivMax] = useState(rangoUnprivInicial[1]);
  const [privMin, setPrivMin] = useState(rangoPrivInicial[0]);
  const [privMax, setPrivMax] = useState(rangoPrivInicial[1]);
  const [unprivCategorico, setUnprivCategorico] = useState(categoricosATexto(sugerido?.unpriv_groups));
  const [privCategorico, setPrivCategorico] = useState(categoricosATexto(sugerido?.priv_groups));
  const [probabilityFormat, setProbabilityFormat] = useState<"scalar" | "list">(
    sugerido?.probability_format ?? "scalar",
  );
  const [probabilityIndex, setProbabilityIndex] = useState(String(sugerido?.probability_index ?? 1));
  // En blanco, la ingesta hereda de la plantilla o de la línea base.
  const [favorableLabel, setFavorableLabel] = useState(
    sugerido?.favorable_label === undefined || sugerido?.favorable_label === null
      ? ""
      : String(sugerido.favorable_label),
  );
  const [features, setFeatures] = useState<Set<string>>(new Set(sugerido?.feature_cols ?? []));

  // En multiclase, las clases, el conjunto favorable y la salida de probabilidad.
  const multiclase = project ? capacidades(project.task_type).favorables === "conjunto" : false;
  // Una regresión no tiene probabilidad ni valor favorable; el rango vive en la plantilla.
  const regresion = project ? capacidades(project.task_type).rangoFavorable : false;
  const mc = useMapeoMulticlase({ multiclase, project, sugerido, columnas, probabilityCol, setProbabilityCol });
  const clases = mc.clases;

  // Huella de lo sugerido (plantilla ya aplicada), fijada al montar, para avisar si el usuario se aparta.
  const huella = () =>
    huellaPlantilla({
      favorableLabel: mc.huellaFavorables ?? favorableLabel,
      idCol,
      protectedCol,
      protectedKind,
      features: Array.from(features),
    });
  const [huellaInicial] = useState(huella);
  const seAparta = huellaInicial !== huella();

  const valoresEtiqueta = labelCol.trim() ? valoresDistintos(filasMuestra, labelCol.trim()) : [];

  const alternar = (col: string) =>
    setFeatures((prev) => {
      const next = new Set(prev);
      if (next.has(col)) next.delete(col);
      else next.add(col);
      return next;
    });

  const puedeGuardar =
    (esFeedback || predictionCol.trim().length > 0) &&
    (esFeedback ? labelCol.trim().length > 0 : true) &&
    (!idColObligatorio || idCol.trim().length > 0) &&
    !mc.probACaballo;

  const guardar = () => {
    if (!puedeGuardar) return;
    void onGuardar({
      mapping: {
        prediction_col: esFeedback ? null : predictionCol.trim(),
        probability_col: regresion ? null : probabilityCol.trim() || null,
        probability_format: probabilityFormat,
        probability_index: Number(probabilityIndex) || 1,
        label_col: labelCol.trim() || null,
        id_col: idCol.trim() || null,
        timestamp_col: timestampCol.trim() || null,
        protected_attr_col: protectedCol.trim() || null,
        protected_kind: protectedKind,
        unpriv_groups:
          protectedKind === "numeric_ranges" ? rangoNumerico(unprivMin, unprivMax) : textoACategoricos(unprivCategorico),
        priv_groups:
          protectedKind === "numeric_ranges" ? rangoNumerico(privMin, privMax) : textoACategoricos(privCategorico),
        feature_cols: Array.from(features),
        clinician_col: null,
        subgroup_col: null,
        // Vacío se manda como `null` y la ingesta lo hereda.
        favorable_label: regresion ? null : valorFavorable(favorableLabel),
        // En multiclase, `mc.mapeo()` sustituye probabilidad y favorables de binario.
        ...(multiclase ? { classes: clases.map(valorDeClase), probability_cols: mc.columnasProb } : {}),
        ...mc.mapeo(),
      },
    });
  };

  return (
    <div className="flex max-h-[60vh] flex-col gap-4">
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto pr-1">
        {seAparta ? (
          <Alert>
            <AlertDescription>
              Este mapeo se aparta de la plantilla del proyecto: quedará anotado en el diario.
            </AlertDescription>
          </Alert>
        ) : null}
        <MapeoCampos
          mostrarPrediccion={!esFeedback}
          idColObligatorio={idColObligatorio}
          predictionCol={predictionCol}
          setPredictionCol={setPredictionCol}
          probabilityCol={probabilityCol}
          setProbabilityCol={setProbabilityCol}
          labelCol={labelCol}
          setLabelCol={setLabelCol}
          idCol={idCol}
          setIdCol={setIdCol}
          timestampCol={timestampCol}
          setTimestampCol={setTimestampCol}
          protectedCol={protectedCol}
          setProtectedCol={setProtectedCol}
          probabilityFormat={probabilityFormat}
          setProbabilityFormat={setProbabilityFormat}
          probabilityIndex={probabilityIndex}
          setProbabilityIndex={setProbabilityIndex}
          protectedKind={protectedKind}
          setProtectedKind={setProtectedKind}
          unprivMin={unprivMin}
          setUnprivMin={setUnprivMin}
          unprivMax={unprivMax}
          setUnprivMax={setUnprivMax}
          privMin={privMin}
          setPrivMin={setPrivMin}
          privMax={privMax}
          setPrivMax={setPrivMax}
          unprivCategorico={unprivCategorico}
          setUnprivCategorico={setUnprivCategorico}
          privCategorico={privCategorico}
          setPrivCategorico={setPrivCategorico}
          favorableLabel={favorableLabel}
          setFavorableLabel={setFavorableLabel}
          valoresEtiqueta={valoresEtiqueta}
          columnas={columnas}
          features={features}
          alternar={alternar}
          plantilla={project?.mapping_template_json}
          multiclase={mc.campos}
          regresion={regresion}
          soloEtiquetas={esFeedback}
          lote={dataset}
        />
        <AvisoSinProbabilidad visible={!esFeedback && !regresion && mc.sinProbabilidad} />
      </div>
      {error ? (
        <Alert variant="destructive" data-testid="error-mapeo">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <Button className="w-fit" onClick={guardar} disabled={!puedeGuardar || guardando}>
        Guardar mapeo
      </Button>
    </div>
  );
}
