/**
 * Campos de identidad del paso «Datos» del alta (partido de `alta-datos.tsx`
 * para no superar 9 KB): identificador, etiqueta con su valor favorable,
 * predicción, probabilidad y fecha. Cada campo lleva su ayuda y las
 * columnas se eligen entre las del fichero de ejemplo (`mapeo-controles.tsx`).
 */

import type { ReactNode } from "react";

import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AsignacionAlta } from "./alta-roles";
import { AYUDA_ALTA, AYUDA_ALTA_MULTICLASE, AYUDA_ALTA_REGRESION } from "./alta-textos";
import { Ayuda, SelectorColumna } from "./mapeo-controles";
import { ANCLA_CLASE_FAVORABLE, EnlaceFormato } from "./subida-enlace-formato";

export type ColumnasAlta = Omit<AsignacionAlta, "protectedCol" | "probabilidadPorColumna">;

interface CamposIdentidadProps {
  columnas: string[];
  aceptaFeedback: boolean;
  onAceptaFeedback: (v: boolean) => void;
  cols: ColumnasAlta;
  onAsignar: (parcial: Partial<ColumnasAlta>) => void;
  favorableLabel: string;
  onFavorableLabel: (v: string) => void;
  valoresLabel: string[];
  /** En multiclase, las casillas del conjunto favorable y las probabilidades por clase sustituyen a los dos campos de binario. */
  multiclase?: { favorables: ReactNode; probabilidades: ReactNode };
  /** En regresión, la unidad y el rango favorable sustituyen al valor favorable y a la probabilidad. */
  regresion?: ReactNode;
}

export function CamposIdentidad({
  columnas,
  aceptaFeedback,
  onAceptaFeedback,
  cols,
  onAsignar,
  favorableLabel,
  onFavorableLabel,
  valoresLabel,
  multiclase,
  regresion,
}: CamposIdentidadProps) {
  const ayudaEtiqueta = regresion ? AYUDA_ALTA_REGRESION.etiqueta : multiclase ? AYUDA_ALTA_MULTICLASE.etiqueta : AYUDA_ALTA.etiqueta;
  const ayudaPrediccion = regresion ? AYUDA_ALTA_REGRESION.prediccion : multiclase ? AYUDA_ALTA_MULTICLASE.prediccion : AYUDA_ALTA.prediccion;
  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={aceptaFeedback} onChange={(e) => onAceptaFeedback(e.target.checked)} />
        Este modelo va a recibir etiquetas reales por identificador (feedback)
      </label>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <SelectorColumna
          id="alta-id-col"
          etiqueta={`Identificador${aceptaFeedback ? " (obligatorio)" : " (opcional)"}`}
          valor={cols.idCol}
          onChange={(v) => onAsignar({ idCol: v })}
          columnas={columnas}
          ayuda={AYUDA_ALTA.identificador}
        />
        <SelectorColumna
          id="alta-label-col"
          etiqueta="Columna de etiqueta"
          valor={cols.labelCol}
          onChange={(v) => onAsignar({ labelCol: v })}
          columnas={columnas}
          ayuda={ayudaEtiqueta}
        />
      </div>
      {multiclase || regresion ? null : (
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="alta-favorable">Valor favorable (obligatorio)</Label>
        {/* Se elige entre los valores detectados de la columna de etiqueta. */}
        <Select value={favorableLabel} onValueChange={onFavorableLabel} disabled={valoresLabel.length === 0}>
          <SelectTrigger id="alta-favorable" className="w-full sm:w-1/2" aria-describedby="alta-favorable-ayuda">
            <SelectValue
              placeholder={valoresLabel.length === 0 ? "Elige antes la columna de etiqueta" : "Elige un valor"}
            />
          </SelectTrigger>
          <SelectContent>
            {valoresLabel.map((v) => (
              <SelectItem key={v} value={v}>
                {v}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Ayuda id="alta-favorable-ayuda">{AYUDA_ALTA.favorable}</Ayuda>
        <EnlaceFormato texto="Cómo decidir la clase favorable" ancla={ANCLA_CLASE_FAVORABLE} nuevaPestana className="w-fit text-xs" />
      </div>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <SelectorColumna
          id="alta-prediction-col"
          etiqueta="Columna de predicción (opcional)"
          valor={cols.predictionCol}
          onChange={(v) => onAsignar({ predictionCol: v })}
          columnas={columnas}
          ayuda={ayudaPrediccion}
          ninguna="Sin fijar"
        />
        {multiclase || regresion ? null : (
          <SelectorColumna
            id="alta-probability-col"
            etiqueta="Columna de probabilidad (opcional)"
            valor={cols.probabilityCol}
            onChange={(v) => onAsignar({ probabilityCol: v })}
            columnas={columnas}
            ayuda={AYUDA_ALTA.probabilidad}
            ninguna="Sin fijar"
          />
        )}
      </div>
      {multiclase ? (
        <>
          {multiclase.favorables}
          {multiclase.probabilidades}
        </>
      ) : null}
      {regresion}
    </div>
  );
}

export function Checklist({
  etiqueta,
  opciones,
  elegidos,
  onAlternar,
}: {
  etiqueta: string;
  opciones: string[];
  elegidos: Set<string>;
  onAlternar: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>
        {etiqueta} ({elegidos.size} elegidos)
      </Label>
      <div className="flex max-h-32 flex-col gap-1 overflow-y-auto rounded-md border border-border p-2 text-sm">
        {opciones.length === 0 ? (
          <p className="text-xs text-muted-foreground">Sin valores vistos todavía: elige antes la columna.</p>
        ) : null}
        {opciones.map((v) => (
          <label key={v} className="flex items-center gap-2">
            <input type="checkbox" checked={elegidos.has(v)} onChange={() => onAlternar(v)} />
            {v}
          </label>
        ))}
      </div>
    </div>
  );
}
