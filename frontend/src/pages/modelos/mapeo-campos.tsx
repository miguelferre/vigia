/**
 * Selectores de columnas y atributo protegido del formulario de mapeo
 * (partido de `mapeo-dataset.tsx` para quedar por debajo de 9 KB).
 */

import type { ReactNode } from "react";

import type { Dataset, ProtectedKind } from "@/api/types";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AYUDA_ALTA_REGRESION } from "./alta-textos";
import { AvisoSinEtiqueta, esLoteSinEtiqueta } from "./aviso-sin-etiqueta";
import { AYUDA_MAPEO, AYUDA_MAPEO_MULTICLASE } from "./etiquetas";
import { Ayuda, Campo, RangoCampo, SelectorColumna } from "./mapeo-controles";
import { CampoFavorable } from "./mapeo-favorable";
import { CaracteristicasMapeo } from "./mapeo-caracteristicas";
import { FormatoProbabilidad } from "./mapeo-formato-probabilidad";

interface Props {
  /** Un dataset `feedback` no pide columna de predicción. */
  mostrarPrediccion?: boolean;
  /** `id_col` obligatorio en `combined`/`payload` salvo `acepta_feedback=false`. */
  idColObligatorio?: boolean;
  predictionCol: string;
  setPredictionCol: (v: string) => void;
  probabilityCol: string;
  setProbabilityCol: (v: string) => void;
  labelCol: string;
  setLabelCol: (v: string) => void;
  idCol: string;
  setIdCol: (v: string) => void;
  timestampCol: string;
  setTimestampCol: (v: string) => void;
  protectedCol: string;
  setProtectedCol: (v: string) => void;
  probabilityFormat: "scalar" | "list";
  setProbabilityFormat: (v: "scalar" | "list") => void;
  probabilityIndex: string;
  setProbabilityIndex: (v: string) => void;
  protectedKind: ProtectedKind;
  setProtectedKind: (v: ProtectedKind) => void;
  unprivMin: string;
  setUnprivMin: (v: string) => void;
  unprivMax: string;
  setUnprivMax: (v: string) => void;
  privMin: string;
  setPrivMin: (v: string) => void;
  privMax: string;
  setPrivMax: (v: string) => void;
  unprivCategorico: string;
  setUnprivCategorico: (v: string) => void;
  privCategorico: string;
  setPrivCategorico: (v: string) => void;
  favorableLabel: string;
  setFavorableLabel: (v: string) => void;
  /** Valores vistos en la columna de etiqueta, para elegir el favorable. */
  valoresEtiqueta?: string[];
  columnas: string[];
  features: Set<string>;
  alternar: (col: string) => void;
  /** `Project.mapping_template_json`: las columnas que la plantilla nombra y el fichero puede no traer. */
  plantilla?: Record<string, unknown> | null;
  /** En multiclase, probabilidad por clase y clases favorables sustituyen a los campos de binario. */
  multiclase?: ReactNode;
  /** En regresión no hay probabilidad ni valor favorable; el rango vive en la plantilla. */
  regresion?: boolean;
  /**
   * Un fichero de etiquetas tardías solo trae el id y la etiqueta (y
   * quizá la fecha). No se piden el atributo protegido, las variables ni
   * nada de la salida del modelo.
   */
  soloEtiquetas?: boolean;
  /** El dataset que se mapea; un lote de producción sin etiqueta lleva un aviso neutro, no el rojo de la plantilla. */
  lote?: Pick<Dataset, "kind" | "role">;
}

export default function MapeoCampos({
  mostrarPrediccion = true,
  idColObligatorio = false,
  valoresEtiqueta = [],
  plantilla = null,
  multiclase = null,
  regresion = false,
  soloEtiquetas = false,
  lote,
  ...p
}: Props) {
  const sinBinario = multiclase !== null || regresion;
  const sinSalida = sinBinario || soloEtiquetas;
  const deLaPlantilla = (campo: string): string | null => {
    const v = plantilla?.[campo];
    return typeof v === "string" && v !== "" ? v : null;
  };
  const sinEtiqueta = lote !== undefined && esLoteSinEtiqueta(lote, p.labelCol);
  return (
    <>
      {lote ? <AvisoSinEtiqueta dataset={lote} labelCol={p.labelCol} /> : null}
      <div className="grid grid-cols-1 items-start gap-3 sm:grid-cols-2">
        {mostrarPrediccion ? (
          <SelectorColumna
            id="mc-columna-de-prediccion"
            etiqueta="Columna de predicción"
            valor={p.predictionCol}
            onChange={p.setPredictionCol}
            columnas={p.columnas}
            ayuda={regresion ? AYUDA_ALTA_REGRESION.prediccion : multiclase ? AYUDA_MAPEO_MULTICLASE.prediccion : AYUDA_MAPEO.prediccion}
            plantillaCol={deLaPlantilla("prediction_col")}
          />
        ) : null}
        {sinSalida ? null : (
          <SelectorColumna
            id="mc-columna-de-probabilidad"
            etiqueta="Columna de probabilidad"
            valor={p.probabilityCol}
            onChange={p.setProbabilityCol}
            columnas={p.columnas}
            ayuda={AYUDA_MAPEO.probabilidad}
            ninguna="Sin probabilidad"
            plantillaCol={deLaPlantilla("probability_col")}
          />
        )}
        <SelectorColumna
          id="mc-columna-de-etiqueta"
          etiqueta="Columna de etiqueta"
          valor={p.labelCol}
          onChange={p.setLabelCol}
          columnas={p.columnas}
          ayuda={regresion ? AYUDA_ALTA_REGRESION.etiqueta : multiclase ? AYUDA_MAPEO_MULTICLASE.etiqueta : AYUDA_MAPEO.etiqueta}
          ninguna="Sin etiqueta"
          plantillaCol={sinEtiqueta ? null : deLaPlantilla("label_col")}
        />
        <SelectorColumna
          id="mc-columna-de-id"
          etiqueta={idColObligatorio ? "Columna de id (obligatoria)" : "Columna de id"}
          valor={p.idCol}
          onChange={p.setIdCol}
          columnas={p.columnas}
          ayuda={AYUDA_MAPEO.identificador}
          plantillaCol={deLaPlantilla("id_col")}
        />
        <SelectorColumna
          id="mc-columna-de-fecha"
          etiqueta="Columna de fecha"
          valor={p.timestampCol}
          onChange={p.setTimestampCol}
          columnas={p.columnas}
          ayuda={AYUDA_MAPEO.fecha}
          ninguna="Sin fecha"
          plantillaCol={deLaPlantilla("timestamp_col")}
        />
        {soloEtiquetas ? null : (
        <SelectorColumna
          id="mc-columna-protegida"
          etiqueta="Columna protegida"
          valor={p.protectedCol}
          onChange={p.setProtectedCol}
          columnas={p.columnas}
          ayuda={AYUDA_MAPEO.columnaProtegida}
          ninguna="Sin atributo protegido"
          plantillaCol={deLaPlantilla("protected_attr_col")}
        />
        )}
      </div>
      {sinSalida ? null : (
        <FormatoProbabilidad
          formato={p.probabilityFormat}
          onFormato={p.setProbabilityFormat}
          indice={p.probabilityIndex}
          onIndice={p.setProbabilityIndex}
        />
      )}
      {soloEtiquetas ? null : (
        <>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="mc-tipo-atributo">Tipo de atributo protegido</Label>
        <Select value={p.protectedKind} onValueChange={(v) => p.setProtectedKind(v as ProtectedKind)}>
          <SelectTrigger id="mc-tipo-atributo" aria-describedby="mc-tipo-atributo-ayuda">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="numeric_ranges">Rangos numéricos</SelectItem>
            <SelectItem value="categorical">Categórico</SelectItem>
          </SelectContent>
        </Select>
        <Ayuda id="mc-tipo-atributo-ayuda">{AYUDA_MAPEO.tipoAtributo}</Ayuda>
      </div>
      {p.protectedKind === "numeric_ranges" ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <RangoCampo
            etiqueta="Grupo supervisado"
            min={p.unprivMin}
            max={p.unprivMax}
            onMin={p.setUnprivMin}
            onMax={p.setUnprivMax}
          />
          <RangoCampo
            etiqueta="Grupo de referencia"
            min={p.privMin}
            max={p.privMax}
            onMin={p.setPrivMin}
            onMax={p.setPrivMax}
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Campo
            etiqueta="Grupo supervisado (valores separados por comas)"
            valor={p.unprivCategorico}
            onChange={p.setUnprivCategorico}
          />
          <Campo
            etiqueta="Grupo de referencia (valores separados por comas)"
            valor={p.privCategorico}
            onChange={p.setPrivCategorico}
          />
        </div>
      )}
        </>
      )}
      {soloEtiquetas ? null : multiclase ?? (regresion ? null : (
        <CampoFavorable valor={p.favorableLabel} onChange={p.setFavorableLabel} valores={valoresEtiqueta} />
      ))}
      {soloEtiquetas ? null : (
        <CaracteristicasMapeo columnas={p.columnas} features={p.features} alternar={p.alternar} />
      )}
    </>
  );
}
