/**
 * Campos del mapeo de un dataset que cambian en un proyecto multiclase:
 * el conjunto favorable (casillas) y la salida de probabilidad, que
 * es una columna por clase o una lista en una sola columna. Sustituyen al
 * «Valor favorable» y al formato escalar de binario en `mapeo-campos.tsx`.
 */

import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AYUDA_MAPEO_MULTICLASE } from "./etiquetas";
import { ListaFavorables, SelectoresProbabilidad } from "./clases-controles";
import { Ayuda, SelectorColumna } from "./mapeo-controles";

export type ModoProbabilidad = "cols" | "list";

interface Props {
  clases: string[];
  favorables: string[];
  onAlternarFavorable: (clase: string) => void;
  modo: ModoProbabilidad;
  onModo: (m: ModoProbabilidad) => void;
  /** Modo «una columna por clase»: la columna de cada clase. */
  probCols: Record<string, string>;
  onProbCol: (clase: string, columna: string) => void;
  /** Modo «lista»: la columna con las `k` probabilidades. */
  probabilityCol: string;
  onProbabilityCol: (v: string) => void;
  columnas: string[];
}

export function CamposMulticlase(p: Props) {
  return (
    <>
      {p.clases.length > 0 ? (
        <p className="text-xs text-muted-foreground" data-testid="mapeo-clases">
          {p.clases.length} clases: {p.clases.join(", ")}.
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Las clases se toman del dataset de la línea base: aquí no hay ninguna declarada todavía.
        </p>
      )}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="mc-formato-probabilidad">Formato de la probabilidad</Label>
        <Select value={p.modo} onValueChange={(v) => p.onModo(v as ModoProbabilidad)}>
          <SelectTrigger id="mc-formato-probabilidad" aria-describedby="mc-formato-probabilidad-ayuda">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="cols">Una columna por clase</SelectItem>
            <SelectItem value="list">Lista en una columna</SelectItem>
          </SelectContent>
        </Select>
        <Ayuda id="mc-formato-probabilidad-ayuda">{AYUDA_MAPEO_MULTICLASE.formatoProbabilidad}</Ayuda>
      </div>
      {p.modo === "cols" ? (
        <SelectoresProbabilidad
          idBase="mc-prob"
          clases={p.clases}
          columnas={p.columnas}
          valores={p.probCols}
          onCambiar={p.onProbCol}
          ayuda={AYUDA_MAPEO_MULTICLASE.probabilidad}
        />
      ) : (
        <SelectorColumna
          id="mc-columna-de-probabilidad"
          etiqueta="Columna con la lista de probabilidades"
          valor={p.probabilityCol}
          onChange={p.onProbabilityCol}
          columnas={p.columnas}
          ayuda={AYUDA_MAPEO_MULTICLASE.probabilidad}
          ninguna="Sin probabilidad"
        />
      )}
      <ListaFavorables
        idBase="mc-favorables"
        etiqueta="Clases favorables"
        ayuda={`${AYUDA_MAPEO_MULTICLASE.favorable} Sin ninguna marcada, hereda las de la plantilla o las de la línea base.`}
        clases={p.clases}
        favorables={p.favorables}
        obligatoria={false}
        onAlternar={p.onAlternarFavorable}
      />
    </>
  );
}
