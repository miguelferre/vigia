/**
 * «Registrar la decisión» (hito 4 del protocolo): al menos una
 * acción del catálogo (`GET /alerts/catalog`, con «seguir vigilando»
 * para la decisión sin medidas), cada una con una nota opcional, además del
 * motivo general de `MotivoDialog`.
 *
 * Con «Registrar riesgo» marcada, al confirmar se abre el formulario del
 * riesgo: la casilla anota la decisión y el formulario crea el riesgo.
 *
 * Aparte de `HitoDialogos.tsx` (que ya rozaba 9 KB con esta pieza dentro):
 * mismo patrón de mutación propia (`acciones.tsx`) e invalidación de
 * `qk.alert` y `["alerts"]`.
 */

import { lazy, Suspense, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { qk } from "@/api/queries";
import type { ActorBody, Alert, AlertCatalogItem, AlertDecideBody, ListResponse } from "@/api/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EJEMPLO_MOTIVO, MotivoDialog } from "@/components/vigia";
import { ETIQUETA_HITO_BOTON } from "./HitoDialogos";
import type { DialogoHitoProps } from "./HitoDialogos";

// El formulario del riesgo se abre al confirmar la decisión (mismo chunk que el botón de la alerta).
const DialogoRegistrarRiesgo = lazy(() =>
  import("@/pages/riesgos/RegistrarRiesgo").then((m) => ({ default: m.DialogoRegistrarRiesgo })),
);

/** Casilla propia (sin `components/ui/checkbox`): nativa, accesible. */
function CasillaAccion({
  id,
  checked,
  onCheckedChange,
  etiqueta,
}: {
  id: string;
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
  etiqueta: string;
}) {
  return (
    <label htmlFor={id} className="flex flex-1 items-center gap-2 text-md">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onCheckedChange(e.target.checked)}
        className="size-4 rounded-[3px] border-border accent-foreground"
      />
      {etiqueta}
    </label>
  );
}

export function DialogoDecidir({ alertId, open, onOpenChange }: DialogoHitoProps) {
  const [marcadas, setMarcadas] = useState<Record<string, boolean>>({});
  const [notas, setNotas] = useState<Record<string, string>>({});
  const [riesgoAbierto, setRiesgoAbierto] = useState(false);
  const queryClient = useQueryClient();

  const catalogo = useQuery({
    queryKey: qk.alertCatalog(),
    queryFn: () => api.get<ListResponse<AlertCatalogItem>>("/alerts/catalog"),
  });
  // Misma consulta que el detalle y el panel de la alerta (clave y función iguales).
  const alerta = useQuery({
    queryKey: qk.alert(alertId),
    queryFn: () => api.get<Alert>(`/alerts/${alertId}`),
    enabled: alertId !== null,
  });
  const claves = Object.keys(marcadas).filter((k) => marcadas[k]);

  const mutacion = useMutation({
    mutationFn: (cuerpo: ActorBody) =>
      api.post<Alert>(`/alerts/${alertId}/decide`, {
        ...cuerpo,
        acciones: claves.map((key) => ({ key, notes: notas[key]?.trim() || null })),
      } satisfies AlertDecideBody),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: qk.alert(alertId) }),
        queryClient.invalidateQueries({ queryKey: ["alerts"] }),
      ]);
      toast.success("Decisión registrada.");
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  return (
    <>
      <MotivoDialog
        open={open}
        onOpenChange={(o) => {
          if (!o) {
            setMarcadas({});
            setNotas({});
          }
          onOpenChange(o);
        }}
        titulo={ETIQUETA_HITO_BOTON.decision}
        etiquetaConfirmar="Registrar"
        ejemplo={EJEMPLO_MOTIVO.decision}
        deshabilitado={claves.length === 0}
        onConfirm={async (cuerpo) => {
          const conRiesgo = marcadas.registrar_riesgo === true;
          await mutacion.mutateAsync(cuerpo);
          if (conRiesgo) setRiesgoAbierto(true);
        }}
      >
        <div className="flex flex-col gap-2">
          <Label>Acciones del catálogo (al menos una)</Label>
          {(catalogo.data?.items ?? []).map((item) => (
            <div key={item.action} className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <CasillaAccion
                  id={`hito-accion-${item.action}`}
                  checked={marcadas[item.action] ?? false}
                  onCheckedChange={(v) => setMarcadas((prev) => ({ ...prev, [item.action]: v }))}
                  etiqueta={item.label}
                />
                <Input
                  value={notas[item.action] ?? ""}
                  onChange={(e) => setNotas((prev) => ({ ...prev, [item.action]: e.target.value }))}
                  placeholder="Nota (opcional)"
                  className="h-8 w-44 flex-none"
                  disabled={!marcadas[item.action]}
                />
              </div>
              {/* La acción anota la decisión y, al confirmar, se abre el formulario del riesgo. */}
              {item.action === "registrar_riesgo" ? (
                <p className="pl-6 text-sm text-muted-foreground">
                  Al registrar la decisión se abre el formulario para crear el riesgo.
                </p>
              ) : null}
            </div>
          ))}
        </div>
      </MotivoDialog>
    {riesgoAbierto && alerta.data ? (
      <Suspense fallback={null}>
        <DialogoRegistrarRiesgo alerta={alerta.data} open={riesgoAbierto} onOpenChange={setRiesgoAbierto} />
      </Suspense>
    ) : null}
    </>
  );
}

export default DialogoDecidir;
