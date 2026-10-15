/**
 * Ajustes (`/ajustes`): lectura y escritura de
 * `GET/PATCH /settings`. La clave nace aquí (patrón `api/queries-<carril>.ts`
 * del contexto común), con la raíz `qk.settings()` ya reservada en
 * `queries.ts` (`RAICES_POR_OBJETO.setting`).
 *
 * El token MCP en claro (`?reveal=true`) vive bajo su propia clave
 * `["settings", "reveal"]`, `staleTime: 0` y fuera de caché entre montajes
 * (no se guarda junto al resto de ajustes.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import { qk, type Opciones } from "./queries";
import type { Settings, SettingsPatchBody } from "./types";

export function useSettings(opciones?: Opciones<Settings>) {
  return useQuery({
    queryKey: qk.settings(),
    queryFn: () => api.get<Settings>("/settings"),
    ...opciones,
  });
}

export const qkSettingsReveal = () => ["settings", "reveal"] as const;

/** `GET /settings?reveal=true`: solo se pide mientras el token está visible. */
export function useSettingsReveal(habilitado: boolean) {
  return useQuery({
    queryKey: qkSettingsReveal(),
    queryFn: () => api.get<Settings>("/settings", { params: { reveal: true } }),
    enabled: habilitado,
    staleTime: 0,
    gcTime: 0,
  });
}

export function usePatchSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cuerpo: SettingsPatchBody) => api.patch<Settings>("/settings", cuerpo),
    onSuccess: (data) => {
      queryClient.setQueryData(qk.settings(), data);
      void queryClient.invalidateQueries({ queryKey: qk.settings() });
    },
  });
}
