/**
 * Estado multiclase del formulario de mapeo de un dataset: clases,
 * conjunto favorable y salida de probabilidad (una columna por clase o una
 * lista). Sale de `mapeo-dataset.tsx` por el límite de 9 KB; en binario
 * (`multiclase = false`) no dibuja nada y `mapeo` no aporta campos.
 */

import { useState } from "react";

import type { ColumnMapping, ColumnMappingOut, ProjectDetail } from "@/api/types";
import { claveClase, favorablesComoLista } from "@/lib/tipo-tarea";
import { probabilidadIncompleta } from "./clases-controles";
import { valorDeClase } from "./clases-multiclase";
import { CamposMulticlase, type ModoProbabilidad } from "./mapeo-multiclase";

interface Entrada {
  /** Lo decide la pantalla con `capacidades(task_type)` (por tipo de tarea, sin comparar cadenas). */
  multiclase: boolean;
  project?: Pick<ProjectDetail, "classes"> | null;
  sugerido?: ColumnMappingOut | null;
  columnas: string[];
  probabilityCol: string;
  setProbabilityCol: (v: string) => void;
}

export function useMapeoMulticlase({ multiclase, project, sugerido, columnas, probabilityCol, setProbabilityCol }: Entrada) {
  const clases = multiclase
    ? ((sugerido?.classes?.length ? sugerido.classes : project?.classes) ?? []).map(claveClase)
    : [];
  const [favorables, setFavorables] = useState<string[]>(() => favorablesComoLista(sugerido?.favorable_label));
  const [modoProb, setModoProb] = useState<ModoProbabilidad>(
    sugerido?.probability_format === "list" && !(sugerido?.probability_cols?.length ?? 0) ? "list" : "cols",
  );
  const [probCols, setProbCols] = useState<Record<string, string>>(() => {
    const sugeridas = sugerido?.probability_cols ?? [];
    return Object.fromEntries(clases.map((c, i) => [c, sugeridas[i] ?? ""]));
  });
  const probTodas = clases.length > 0 && clases.every((c) => (probCols[c] ?? "") !== "");

  /** Campos del mapeo que sustituyen a los de binario; `{}` en binario. */
  const mapeo = (): Partial<ColumnMapping> =>
    multiclase
      ? {
          probability_col: modoProb === "list" ? probabilityCol.trim() || null : null,
          probability_format: modoProb === "list" ? "list" : "scalar",
          probability_index: 1,
          favorable_label: favorables.length > 0 ? clases.filter((c) => favorables.includes(c)).map(valorDeClase) : null,
        }
      : {};

  const sinProbabilidad = multiclase && modoProb === "cols" ? !clases.some((c) => (probCols[c] ?? "") !== "") : probabilityCol.trim() === "";

  return {
    /** Clases del proyecto o de lo sugerido (vacío en binario). */
    clases,
    /** Una columna de probabilidad por clase, solo si están todas elegidas y el modo es «cols». */
    columnasProb: modoProb === "cols" && probTodas ? clases.map((c) => probCols[c]) : [],
    /** Huella del conjunto favorable para detectar que el mapeo se aparta de la plantilla; `null` en binario. */
    huellaFavorables: multiclase ? favorables.join("|") : null,
    /** Probabilidad por clase a medias: bloquea el guardado. */
    probACaballo: modoProb === "cols" && probabilidadIncompleta(clases, probCols),
    sinProbabilidad,
    mapeo,
    campos: multiclase ? (
      <CamposMulticlase
        clases={clases}
        favorables={favorables}
        onAlternarFavorable={(c) =>
          setFavorables((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))
        }
        modo={modoProb}
        onModo={setModoProb}
        probCols={probCols}
        onProbCol={(c, col) => setProbCols((prev) => ({ ...prev, [c]: col }))}
        probabilityCol={probabilityCol}
        onProbabilityCol={setProbabilityCol}
        columnas={columnas}
      />
    ) : undefined,
  };
}
