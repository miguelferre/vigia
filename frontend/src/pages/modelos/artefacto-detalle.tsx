/**
 * Ficha del artefacto de una versión de modelo (tipo, sha256 corto, número
 * de entradas y fecha de subida) para la columna «Artefacto» de
 * la tabla de versiones. Aparte de `versiones-columnas.tsx` para no crecer
 * de más (mismo criterio que `versiones-columnas.tsx` respecto a
 * `versiones.tsx`).
 */

import type { ModelVersion } from "@/api/types";
import { formatoFecha } from "@/lib/metrics";
import { AvisoTipos } from "./aviso-tipos";

const ETIQUETA_TIPO: Record<string, string> = {
  onnx: "ONNX",
  pickle: "Pickle / joblib",
};

export function ArtefactoDetalle({ version }: { version: ModelVersion }) {
  if (!version.artifact_sha256 || !version.artifact_kind) {
    return <span className="text-xs text-muted-foreground">Sin modelo cargado</span>;
  }
  const entradas = Array.isArray(version.artifact_inputs_json) ? version.artifact_inputs_json.length : null;
  return (
    <div className="flex flex-col gap-0.5 text-xs">
      <span className="font-medium">{ETIQUETA_TIPO[version.artifact_kind] ?? version.artifact_kind}</span>
      <span className="text-muted-foreground">sha256 {version.artifact_sha256.slice(0, 8)}…</span>
      {entradas !== null ? (
        <span className="text-muted-foreground">
          {entradas} {entradas === 1 ? "entrada" : "entradas"}
        </span>
      ) : null}
      {version.artifact_uploaded_at ? (
        <span className="text-muted-foreground">Subido {formatoFecha(version.artifact_uploaded_at)}</span>
      ) : null}
      <AvisoTipos aviso={version.aviso_tipos} />
    </div>
  );
}

export default ArtefactoDetalle;
