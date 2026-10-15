/**
 * tipos y consulta del paso «Umbrales» del alta, partidos de
 * `queries.ts` como el resto de módulos hoja. `MappingTemplate`,
 * `ThresholdsProposal` y compañía no tienen alias en `@/api/types`
 * (`types-base.ts`/`types-domain.ts`):
 * se leen directo de `Schemas`, el mismo patrón que usan esos módulos.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import { qk, STALE_MS, type Opciones } from "./queries";
import type { Schemas } from "./types";

export type MappingTemplate = Schemas["MappingTemplate"];
export type ThresholdsProposal = Schemas["ThresholdsProposal"];
export type ThresholdsProposalMonitor = Schemas["ThresholdsProposalMonitor"];
export type PropuestaUmbral = Schemas["PropuestaUmbral"];
export type DatasetDialect = Schemas["DatasetDialect"];

/** Origen de un umbral guardado; `fabrica` nunca se manda, solo se lee. */
export type ThresholdOrigen = "linea_base" | "fabricante" | "criterio_clinico" | "politica_organizacion" | "fabrica";

/** Entrada de `Monitor.thresholds.thresholds` con origen y nota (`core/schema.py:Threshold`). */
export interface ThresholdEntryConOrigen {
  metric_key: string;
  kind: "lower_limit" | "upper_limit";
  value: number;
  origen?: ThresholdOrigen;
  nota?: string;
}

/**
 * `GET /projects/{id}/thresholds/proposal` (paso «Umbrales» del alta):
 * 409 sin línea base congelada, que el llamador distingue con
 * `error instanceof ApiError && error.status === 409` para el estado vacío.
 */
export function useThresholdsProposal(
  projectId: number | null,
  tamanoLote: number,
  opciones?: Opciones<ThresholdsProposal>,
) {
  return useQuery({
    queryKey: qk.thresholdsProposal(projectId, tamanoLote),
    queryFn: () =>
      api.get<ThresholdsProposal>(`/projects/${projectId}/thresholds/proposal`, {
        params: { tamano_lote: tamanoLote },
      }),
    enabled: projectId !== null,
    staleTime: STALE_MS,
    retry: false,
    ...opciones,
  });
}
