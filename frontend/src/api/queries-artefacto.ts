/**
 * Subida del artefacto de una versión de modelo (`POST
 * /model-versions/{id}/artifact`). Sin lectura propia: la ficha del artefacto viaja ya en
 * `ModelVersion` (`GET /projects/{id}` -> `useProject`), que se invalida al
 * terminar para que la tabla de versiones se refresque sola.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { Schemas } from "./types";

export interface SubirArtefactoInput {
  versionId: number;
  file: File;
  artifactKind: "onnx" | "pickle";
  /** Solo se manda `true` con `artifactKind: "pickle"` y la casilla marcada. */
  confirmacionPickle: boolean;
}

export function useSubirArtefacto() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ versionId, file, artifactKind, confirmacionPickle }: SubirArtefactoInput) => {
      const form = new FormData();
      form.append("file", file);
      form.append("artifact_kind", artifactKind);
      form.append("confirmacion_pickle", String(confirmacionPickle));
      return api.upload<Schemas["ModelArtifactUploadResponse"]>(
        `/model-versions/${versionId}/artifact`,
        form,
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["state"] });
    },
  });
}
