/**
 * Campos del diálogo «Editar plantilla de mapeo». Texto libre con
 * sugerencias de columnas (`datalist`) tomadas de los datasets ya subidos: la
 * plantilla se puede editar aunque el proyecto no tenga ninguno todavía.
 */

import type { ProtectedKind } from "@/api/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { AYUDA_MAPEO_MULTICLASE } from "./etiquetas";
import { ListaFavorables } from "./clases-controles";
import { CamposRegresion } from "./alta-regresion";
import type { BorradorPlantilla } from "./configuracion-plantilla-helpers";

const ID_COLUMNAS = "cfg-plantilla-columnas";

interface Props {
  borrador: BorradorPlantilla;
  onCambiar: (parcial: Partial<BorradorPlantilla>) => void;
  /** Columnas vistas en los datasets del proyecto (sugerencias, no restricción). */
  columnas: string[];
}

function CampoColumna({
  id,
  etiqueta,
  valor,
  onChange,
}: {
  id: string;
  etiqueta: string;
  valor: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{etiqueta}</Label>
      <Input id={id} list={ID_COLUMNAS} value={valor} autoComplete="off" onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

export function PlantillaCampos({ borrador: b, onCambiar, columnas }: Props) {
  const numerico = b.protectedKind === "numeric_ranges";
  return (
    <div className="flex max-h-[45vh] flex-col gap-3 overflow-y-auto pr-1">
      <datalist id={ID_COLUMNAS}>
        {columnas.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
      <p className="text-xs text-muted-foreground">
        Una columna vacía queda sin fijar. Vale para las próximas subidas: no cambia lo que ya está
        ingerido.
      </p>
      {b.multiclase ? (
        <ListaFavorables
          idBase="cfg-plantilla-favorables"
          etiqueta="Clases favorables"
          ayuda={`${AYUDA_MAPEO_MULTICLASE.favorable} Sin ninguna marcada, el modelo no tiene conjunto favorable y la equidad no se calcula.`}
          clases={b.clases}
          favorables={b.favorables}
          obligatoria={false}
          onAlternar={(c) =>
            onCambiar({
              favorables: b.favorables.includes(c) ? b.favorables.filter((x) => x !== c) : [...b.favorables, c],
            })
          }
        />
      ) : null}
      <div className="grid grid-cols-2 gap-3">
        {b.multiclase || b.regresion ? null : (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cfg-plantilla-favorable">Valor favorable</Label>
            <Input
              id="cfg-plantilla-favorable"
              value={b.favorable}
              autoComplete="off"
              onChange={(e) => onCambiar({ favorable: e.target.value })}
            />
          </div>
        )}
        <CampoColumna id="cfg-plantilla-id" etiqueta="Identificador" valor={b.idCol} onChange={(v) => onCambiar({ idCol: v })} />
        <CampoColumna id="cfg-plantilla-label" etiqueta="Columna de etiqueta" valor={b.labelCol} onChange={(v) => onCambiar({ labelCol: v })} />
        <CampoColumna id="cfg-plantilla-prediction" etiqueta="Columna de predicción" valor={b.predictionCol} onChange={(v) => onCambiar({ predictionCol: v })} />
        {b.multiclase || b.regresion ? null : (
          <CampoColumna id="cfg-plantilla-probability" etiqueta="Columna de probabilidad" valor={b.probabilityCol} onChange={(v) => onCambiar({ probabilityCol: v })} />
        )}
        <CampoColumna id="cfg-plantilla-timestamp" etiqueta="Columna de fecha" valor={b.timestampCol} onChange={(v) => onCambiar({ timestampCol: v })} />
      </div>
      {b.regresion ? (
        <CamposRegresion
          idBase="cfg-plantilla"
          unidadTexto={b.unidad}
          onUnidad={(unidad) => onCambiar({ unidad })}
          intervalos={b.rangos}
          onIntervalos={(rangos) => onCambiar({ rangos })}
        />
      ) : null}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="cfg-plantilla-features">Variables (separadas por comas)</Label>
        <Textarea
          id="cfg-plantilla-features"
          rows={3}
          value={b.features}
          onChange={(e) => onCambiar({ features: e.target.value })}
        />
        <p className="text-xs text-muted-foreground">
          Las columnas que el modelo recibe. El id, la etiqueta, la predicción, la probabilidad y la
          fecha no cuentan y se quitan solas.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <CampoColumna id="cfg-plantilla-protegida" etiqueta="Columna protegida" valor={b.protectedCol} onChange={(v) => onCambiar({ protectedCol: v })} />
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cfg-plantilla-tipo">Tipo de atributo</Label>
          <Select value={b.protectedKind} onValueChange={(v) => onCambiar({ protectedKind: v as ProtectedKind })}>
            <SelectTrigger id="cfg-plantilla-tipo">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="categorical">Categórico</SelectItem>
              <SelectItem value="numeric_ranges">Rangos numéricos</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cfg-plantilla-unpriv">Grupo supervisado</Label>
          <Input id="cfg-plantilla-unpriv" value={b.unpriv} autoComplete="off" onChange={(e) => onCambiar({ unpriv: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cfg-plantilla-priv">Grupo de referencia</Label>
          <Input id="cfg-plantilla-priv" value={b.priv} autoComplete="off" onChange={(e) => onCambiar({ priv: e.target.value })} />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        {numerico
          ? "Rangos como mínimo..máximo, separados por comas (por ejemplo 0..40, 41..120)."
          : "Valores de la columna protegida, separados por comas."}
      </p>
    </div>
  );
}
