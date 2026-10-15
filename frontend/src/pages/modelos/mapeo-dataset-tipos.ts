/**
 * Tipos del formulario de mapeo de un dataset (`mapeo-dataset.tsx`): el
 * resultado y las propiedades. Salen del fichero original por el límite de 9 KB.
 */

import type { ColumnMapping, ColumnMappingOut, Dataset, ProjectDetail } from "@/api/types";

export interface MapeoResultado {
  mapping: ColumnMapping;
}

export interface MapeoDatasetProps {
  dataset: Dataset;
  onGuardar: (r: MapeoResultado) => void | Promise<void>;
  guardando?: boolean;
  /**
   * Mapeo de `GET /demo/scenarios` (`upload_mapping`): manda
   * sobre `dataset.suggested_mapping` cuando la subida viene precargada
   * desde la demo (`?demo=subir`), para que el usuario solo confirme.
   */
  mapeoInicial?: ColumnMappingOut | null;
  /**
   * Proyecto del dataset: `acepta_feedback=false` libera
   * `id_col` de ser obligatorio; sin proyecto (pantallas que no lo tienen a
   * mano), se asume `true`, la posición más exigente.
   */
  project?: Pick<ProjectDetail, "acepta_feedback" | "mapping_template_json" | "task_type" | "classes"> | null;
  /**
   * Filas de muestra del fichero (texto), de donde salen los valores
   * de la columna de etiqueta entre los que se elige el favorable.
   */
  filasMuestra?: Record<string, string>[];
  /** Texto del 422 de `PUT /datasets/{id}/mapping`, enseñado junto al botón. */
  error?: string | null;
}
