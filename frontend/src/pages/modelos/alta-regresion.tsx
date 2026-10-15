/**
 * Unidad y rango favorable de una regresión: el paso «Datos» del
 * alta (`useRegresionAlta`) y el diálogo de la plantilla de Configuración
 * (`CamposRegresion` suelto). Los campos se ven antes de elegir el fichero:
 * «Crear sin plantilla» también fija la unidad y el rango, que no se pueden
 * cambiar después de congelar la línea base. La vista previa dice qué
 * parte de las predicciones del fichero de ejemplo cae en el rango, con la
 * misma regla que `en_rango` del servidor.
 */

import { useState } from "react";
import { PlusIcon, XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatoNumero, textoRangos } from "@/lib/metrics";
import {
  EJEMPLOS_UNIDAD,
  FILA_VACIA,
  leerRangos,
  leerUnidad,
  MAX_RANGOS,
  parteEnRango,
  type FilaRango,
} from "./alta-regresion-rango";
import { AYUDA_ALTA_REGRESION } from "./alta-textos";
import { Ayuda } from "./mapeo-controles";

/** Lo que el alta de una regresión manda en el cuerpo de `POST /api/projects` y en la plantilla. */
export interface RegresionAlta {
  target_unit: string | null;
  favorable_ranges: [number | null, number | null][];
}

interface CamposProps {
  /** Prefijo de los ids, para que el alta y la plantilla no choquen. */
  idBase: string;
  unidadTexto: string;
  onUnidad: (texto: string) => void;
  intervalos: FilaRango[];
  onIntervalos: (filas: FilaRango[]) => void;
  /** Con la muestra del fichero de ejemplo y la columna de predicción, la vista previa del rango. */
  muestra?: { filas: Record<string, string>[]; predictionCol: string };
}

export function CamposRegresion({ idBase, unidadTexto, onUnidad, intervalos, onIntervalos, muestra }: CamposProps) {
  const { unidad, error: errorUnidad } = leerUnidad(unidadTexto);
  const { rangos, error: errorRangos } = leerRangos(intervalos);
  const parte =
    muestra && rangos.length > 0 && muestra.predictionCol !== ""
      ? parteEnRango(
          muestra.filas.map((f) => f[muestra.predictionCol] ?? ""),
          rangos,
        )
      : null;
  const cambia = (i: number, parcial: Partial<FilaRango>) =>
    onIntervalos(intervalos.map((f, j) => (j === i ? { ...f, ...parcial } : f)));
  return (
    <div className="flex flex-col gap-4" data-testid="alta-regresion">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${idBase}-unidad`}>Unidad de la salida (opcional)</Label>
        <Input
          id={`${idBase}-unidad`}
          value={unidadTexto}
          list={`${idBase}-unidad-ejemplos`}
          placeholder="por ejemplo, días"
          autoComplete="off"
          aria-invalid={errorUnidad !== null}
          aria-describedby={`${idBase}-unidad-ayuda`}
          onChange={(e) => onUnidad(e.target.value)}
        />
        <datalist id={`${idBase}-unidad-ejemplos`}>
          {EJEMPLOS_UNIDAD.map((u) => (
            <option key={u} value={u} />
          ))}
        </datalist>
        <Ayuda id={`${idBase}-unidad-ayuda`}>{AYUDA_ALTA_REGRESION.unidad}</Ayuda>
        {errorUnidad ? (
          <p role="alert" className="text-xs text-destructive" data-testid="alta-unidad-error">
            {errorUnidad}
          </p>
        ) : null}
      </div>
      <fieldset className="flex flex-col gap-2" aria-describedby={`${idBase}-rango-ayuda`}>
        <legend className="text-sm font-medium">Rango favorable (opcional)</legend>
        <Ayuda id={`${idBase}-rango-ayuda`}>{AYUDA_ALTA_REGRESION.rango}</Ayuda>
        {intervalos.map((f, i) => (
          <div key={i} className="flex items-end gap-2" data-testid="alta-rango-fila">
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <Label htmlFor={`${idBase}-rango-${i}-min`} className="text-xs">
                {intervalos.length > 1 ? `Intervalo ${i + 1}: desde` : "Desde"}
              </Label>
              <Input
                id={`${idBase}-rango-${i}-min`}
                inputMode="decimal"
                value={f.min}
                placeholder="sin mínimo"
                autoComplete="off"
                onChange={(e) => cambia(i, { min: e.target.value })}
              />
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <Label htmlFor={`${idBase}-rango-${i}-max`} className="text-xs">
                Hasta
              </Label>
              <Input
                id={`${idBase}-rango-${i}-max`}
                inputMode="decimal"
                value={f.max}
                placeholder="sin máximo"
                autoComplete="off"
                onChange={(e) => cambia(i, { max: e.target.value })}
              />
            </div>
            {intervalos.length > 1 ? (
              <Button
                type="button"
                size="icon"
                variant="ghost"
                aria-label={`Quitar el intervalo ${i + 1}`}
                onClick={() => onIntervalos(intervalos.filter((_, j) => j !== i))}
              >
                <XIcon className="size-4" aria-hidden="true" />
              </Button>
            ) : null}
          </div>
        ))}
        {intervalos.length < MAX_RANGOS ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="w-fit"
            onClick={() => onIntervalos([...intervalos, FILA_VACIA])}
          >
            <PlusIcon className="size-4" aria-hidden="true" />
            Añadir otro intervalo
          </Button>
        ) : null}
        {errorRangos ? (
          <p role="alert" className="text-xs text-destructive" data-testid="alta-rango-error">
            {errorRangos}
          </p>
        ) : null}
        {rangos.length > 0 ? (
          <div className="flex flex-col gap-1 rounded-md bg-muted/50 p-2 text-xs" data-testid="alta-rango-vista-previa">
            <p className="font-medium">Cuenta como favorable: {textoRangos(rangos, unidad)}</p>
            {muestra === undefined ? null : muestra.filas.length === 0 ? (
              <p className="text-muted-foreground">
                Elige el fichero de ejemplo para ver qué parte de la línea base cae en el rango.
              </p>
            ) : parte === null ? (
              <p className="text-muted-foreground">
                Elige la columna de predicción para ver qué parte de la línea base cae en el rango.
              </p>
            ) : parte.fraccion === null ? (
              <p className="text-muted-foreground">
                La columna de predicción no trae números en las primeras filas del fichero.
              </p>
            ) : (
              <>
                <p>
                  En las {parte.n.toLocaleString("es-ES")} primeras filas del fichero, el{" "}
                  {formatoNumero(parte.fraccion * 100, 1)} % de las predicciones cae en el rango.
                </p>
                {parte.fraccion === 0 || parte.fraccion === 1 ? (
                  <p className="text-muted-foreground">
                    Todas caen del mismo lado: la equidad por rango no tendría con qué comparar. Revisa los extremos.
                  </p>
                ) : null}
              </>
            )}
          </div>
        ) : null}
      </fieldset>
    </div>
  );
}

interface Entrada {
  activo: boolean;
  /** Filas de la muestra del fichero de ejemplo (`leerColumnasEjemplo`); vacío sin fichero. */
  filas: Record<string, string>[];
  predictionCol: string;
}

/** Estado del alta: con `activo = false` no dibuja nada y no valida. */
export function useRegresionAlta({ activo, filas, predictionCol }: Entrada) {
  const [unidadTexto, setUnidadTexto] = useState("");
  const [intervalos, setIntervalos] = useState<FilaRango[]>([FILA_VACIA]);
  const { unidad, error: errorUnidad } = leerUnidad(unidadTexto);
  const { rangos, error: errorRangos } = leerRangos(intervalos);
  const campos = activo ? (
    <CamposRegresion
      idBase="alta"
      unidadTexto={unidadTexto}
      onUnidad={setUnidadTexto}
      intervalos={intervalos}
      onIntervalos={setIntervalos}
      muestra={{ filas, predictionCol }}
    />
  ) : undefined;
  return {
    campos,
    valido: errorUnidad === null && errorRangos === null,
    valores: { target_unit: unidad, favorable_ranges: rangos } satisfies RegresionAlta,
  };
}
