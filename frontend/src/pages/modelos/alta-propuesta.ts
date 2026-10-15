/**
 * Primera propuesta de papeles del paso «Datos» del alta (partida de
 * `alta-datos.tsx` para no pasar de 9 KB): por el nombre de la columna, con
 * los mismos candidatos que `_suggest_mapping` (`services/ingest.py`).
 */

import type { ColumnasAlta } from "./alta-datos-campos";
import { sugerirColumna, sugerirColumnaFecha } from "./alta-sniff";

export const COLUMNAS_VACIAS: ColumnasAlta = {
  idCol: "",
  labelCol: "",
  predictionCol: "",
  probabilityCol: "",
  timestampCol: "",
};

export function proponerColumnas(columnas: string[]): ColumnasAlta {
  return {
    idCol: sugerirColumna(columnas, "id"),
    labelCol: sugerirColumna(columnas, "label", "target", "y"),
    predictionCol: sugerirColumna(columnas, "prediction", "pred"),
    probabilityCol: sugerirColumna(columnas, "probability", "prob", "proba"),
    timestampCol: sugerirColumnaFecha(columnas) ?? "",
  };
}
