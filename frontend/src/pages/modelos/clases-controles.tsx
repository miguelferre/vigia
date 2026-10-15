/**
 * Controles de clases de un modelo multiclase: casillas del
 * conjunto favorable, una columna de probabilidad por clase y alta de una
 * clase que la muestra del fichero no trae. Los usan el alta, el mapeo de un
 * dataset y la plantilla de configuración.
 */

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { motivoFavorablesNoValidos, normalizarClase } from "./clases-multiclase";
import { Ayuda, SelectorColumna } from "./mapeo-controles";

interface ListaFavorablesProps {
  idBase: string;
  etiqueta: string;
  ayuda: string;
  clases: string[];
  favorables: string[];
  onAlternar: (clase: string) => void;
  /** Sin esta marca, la lista no avisa de un conjunto vacío (herencia en el mapeo de un dataset). */
  obligatoria?: boolean;
}

/** Casillas del conjunto favorable: de una a `k - 1` clases; aviso si se marcan todas. */
export function ListaFavorables({
  idBase,
  etiqueta,
  ayuda,
  clases,
  favorables,
  onAlternar,
  obligatoria = true,
}: ListaFavorablesProps) {
  const motivo = clases.length > 0 && (obligatoria || favorables.length > 0) ? motivoFavorablesNoValidos(clases, favorables) : null;
  return (
    <div className="flex flex-col gap-1.5" data-testid="alta-favorables">
      <Label id={`${idBase}-etiqueta`}>
        {etiqueta} ({favorables.filter((f) => clases.includes(f)).length} marcadas de {clases.length})
      </Label>
      <Ayuda id={`${idBase}-ayuda`}>{ayuda}</Ayuda>
      {clases.length === 0 ? (
        <p className="text-xs text-muted-foreground">Elige antes la columna de predicción o la de etiqueta.</p>
      ) : (
        <div
          role="group"
          aria-labelledby={`${idBase}-etiqueta`}
          aria-describedby={`${idBase}-ayuda`}
          className="flex max-h-40 flex-col gap-1 overflow-y-auto rounded-md border border-border p-2 text-sm"
        >
          {clases.map((clase) => (
            <label key={clase} className="flex items-center gap-2">
              <input type="checkbox" checked={favorables.includes(clase)} onChange={() => onAlternar(clase)} />
              <span className="[overflow-wrap:anywhere]">{clase}</span>
            </label>
          ))}
        </div>
      )}
      {motivo ? (
        <p role="alert" className="text-xs text-destructive" data-testid="alta-favorables-aviso">
          {motivo}
        </p>
      ) : null}
    </div>
  );
}

interface ProbabilidadesProps {
  idBase: string;
  clases: string[];
  columnas: string[];
  /** Columna elegida de cada clase (clave de clase a nombre de columna); vacío si no hay. */
  valores: Record<string, string>;
  onCambiar: (clase: string, columna: string) => void;
  ayuda: string;
}

/** Una columna de probabilidad por clase, en el orden de `classes`. Todas o ninguna. */
export function SelectoresProbabilidad({ idBase, clases, columnas, valores, onCambiar, ayuda }: ProbabilidadesProps) {
  const elegidas = clases.filter((c) => (valores[c] ?? "") !== "").length;
  const incompleta = elegidas > 0 && elegidas < clases.length;
  return (
    <div className="flex flex-col gap-1.5" data-testid="alta-probabilidades">
      <Label id={`${idBase}-etiqueta`}>Probabilidad de cada clase (opcional)</Label>
      <Ayuda id={`${idBase}-ayuda`}>{ayuda}</Ayuda>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {clases.map((clase, i) => (
          <SelectorColumna
            key={clase}
            id={`${idBase}-${i}`}
            etiqueta={`Probabilidad de «${clase}»`}
            valor={valores[clase] ?? ""}
            onChange={(v) => onCambiar(clase, v)}
            columnas={columnas}
            ninguna="Sin fijar"
          />
        ))}
      </div>
      {incompleta ? (
        <p role="alert" className="text-xs text-destructive" data-testid="alta-probabilidades-aviso">
          Hay {elegidas} de {clases.length} columnas de probabilidad. Elige una para cada clase o deja todas sin fijar.
        </p>
      ) : null}
    </div>
  );
}

/** `true` si las columnas de probabilidad están a medias: ni todas ni ninguna. */
export function probabilidadIncompleta(clases: string[], valores: Record<string, string>): boolean {
  const elegidas = clases.filter((c) => (valores[c] ?? "") !== "").length;
  return elegidas > 0 && elegidas < clases.length;
}

/** Añade una clase que la muestra leída del fichero no trae (una clase rara). */
/** Qué se ha leído del fichero de ejemplo, para que la persona sepa si puede faltar una clase. */
export const AYUDA_CLASE_EXTRA_PARCIAL =
  "Solo se han leído los primeros 5 MB del fichero (o se está leyendo): una clase rara que salga más adelante no aparece. Si falta alguna, escríbela aquí.";
export const AYUDA_CLASE_EXTRA_COMPLETA =
  "Se ha leído el fichero entero. Si aun así falta alguna clase, escríbela aquí.";

interface AnadirClaseProps {
  clases: string[];
  onAnadir: (clase: string) => void;
  /** El fichero es mayor que el tope de lectura (o aún se lee): solo se conoce el principio. */
  parcial?: boolean;
}

export function AnadirClase({ clases, onAnadir, parcial = true }: AnadirClaseProps) {
  const [texto, setTexto] = useState("");
  const clase = normalizarClase(texto);
  const repetida = clase !== "" && clases.includes(clase);
  const anadir = () => {
    if (clase === "" || repetida) return;
    onAnadir(clase);
    setTexto("");
  };
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="alta-clase-extra">Añadir una clase que no salga en la muestra</Label>
      <div className="flex gap-2">
        <Input
          id="alta-clase-extra"
          value={texto}
          autoComplete="off"
          className="w-full sm:w-64"
          aria-describedby="alta-clase-extra-ayuda"
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              anadir();
            }
          }}
        />
        <Button type="button" variant="outline" size="sm" disabled={clase === "" || repetida} onClick={anadir}>
          Añadir
        </Button>
      </div>
      <Ayuda id="alta-clase-extra-ayuda">
        {repetida
          ? "Esa clase ya está en la lista."
          : parcial
            ? AYUDA_CLASE_EXTRA_PARCIAL
            : AYUDA_CLASE_EXTRA_COMPLETA}
      </Ayuda>
    </div>
  );
}
