/**
 * Lista de variables del paso «Datos» del alta (partido de
 * `alta-datos.tsx`): las columnas sin otro papel que no parecen fecha ni
 * identificador vienen marcadas; si el usuario marca una que lo parece, aviso
 * en línea. El estado de cada casilla vive en el padre (`decisiones`).
 */

import { useState } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { pareceFecha, pareceIdentificador } from "./alta-sniff";
import {
  AVISO_FECHA_VARIABLE,
  AVISO_ID_VARIABLE,
  AYUDA_ALTA,
  NOTA_PROTEGIDA_VARIABLE,
  SIN_COLUMNAS_LIBRES,
} from "./alta-textos";
import { Ayuda } from "./mapeo-controles";

/** Con más columnas que estas, un campo de filtro por nombre encima de la lista. */
export const COLUMNAS_PARA_FILTRO = 10;

interface Props {
  /** Columnas que pueden ser variables (sin identificador, etiqueta, predicción, probabilidad ni fecha elegidas). */
  opciones: string[];
  marcadas: Set<string>;
  filas: Record<string, string>[];
  onAlternar: (col: string, marcada: boolean) => void;
  /** Columna del atributo protegido ya elegida (vacía si no hay): sale desmarcada, con una nota. */
  protegida?: string;
}

export function VariablesAlta({ opciones, marcadas, filas, onAlternar, protegida = "" }: Props) {
  // Solo oculta casillas: lo marcado (y lo que se guarda) no cambia.
  const [filtro, setFiltro] = useState("");
  const conFiltro = opciones.length > COLUMNAS_PARA_FILTRO;
  const buscado = conFiltro ? filtro.trim().toLowerCase() : "";
  const visibles = buscado === "" ? opciones : opciones.filter((c) => c.toLowerCase().includes(buscado));
  return (
    <div className="flex flex-col gap-1.5">
      <Label id="alta-variables-etiqueta">Variables ({marcadas.size} elegidas)</Label>
      <Ayuda id="alta-variables-ayuda">{AYUDA_ALTA.variables}</Ayuda>
      {conFiltro ? (
        <Input
          type="search"
          value={filtro}
          onChange={(e) => setFiltro(e.target.value)}
          placeholder={`Filtrar las ${opciones.length} columnas por nombre`}
          aria-label="Filtrar las variables por nombre"
          data-testid="alta-variables-filtro"
        />
      ) : null}
      <div
        role="group"
        aria-labelledby="alta-variables-etiqueta"
        aria-describedby="alta-variables-ayuda"
        className="flex max-h-40 flex-col gap-1 overflow-y-auto rounded-md border border-border p-2 text-sm"
      >
        {opciones.length === 0 ? (
          <p className="text-xs text-muted-foreground">{SIN_COLUMNAS_LIBRES}</p>
        ) : null}
        {conFiltro && visibles.length === 0 ? (
          <p className="text-xs text-muted-foreground">Ninguna columna coincide con «{filtro.trim()}».</p>
        ) : null}
        {visibles.map((col) => {
          const marcada = marcadas.has(col);
          const aviso = !marcada
            ? null
            : pareceFecha(col, filas)
              ? AVISO_FECHA_VARIABLE
              : pareceIdentificador(col, filas)
                ? AVISO_ID_VARIABLE
                : null;
          return (
            <div key={col} className="flex flex-col gap-0.5">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={marcada} onChange={() => onAlternar(col, !marcada)} />
                {col}
              </label>
              {!marcada && protegida !== "" && col === protegida ? (
                <p className="pl-6 text-xs text-muted-foreground" data-testid="nota-protegida-variable">
                  <span className="font-medium">{col}:</span> {NOTA_PROTEGIDA_VARIABLE}.
                </p>
              ) : null}
              {aviso ? (
                <p role="status" className="pl-6 text-xs text-destructive" data-testid="aviso-variable">
                  <span className="font-medium">{col}:</span> {aviso}.
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
