/**
 * Panel de acciones de una alerta: catálogo (`GET /alerts/catalog`), motivo
 * y adjunto opcional, enviado a `POST /alerts/{id}/actions`; debajo, las
 * acciones ya registradas.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { qk } from "@/api/queries";
import type { ActorBody, Alert, AlertAction, AlertActionBody, AlertCatalogItem, ListResponse } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { EJEMPLO_MOTIVO, MotivoDialog } from "@/components/vigia";
import { formatoFecha } from "@/lib/metrics";
import { ETIQUETA_ROL } from "@/session/session";
import type { Rol } from "@/api/types";

export interface AccionesProps {
  alertId: number;
  acciones: AlertAction[];
}

export function Acciones({ alertId, acciones }: AccionesProps) {
  const queryClient = useQueryClient();
  const [accion, setAccion] = useState<string>("");
  const [adjunto, setAdjunto] = useState("");
  const [abierto, setAbierto] = useState(false);

  const catalogo = useQuery({
    queryKey: qk.alertCatalog(),
    queryFn: () => api.get<ListResponse<AlertCatalogItem>>("/alerts/catalog"),
  });

  const mutacion = useMutation({
    mutationFn: (cuerpo: ActorBody) =>
      api.post<Alert>(`/alerts/${alertId}/actions`, {
        ...cuerpo,
        action: accion,
        attachment_path: adjunto.trim() || null,
      } satisfies AlertActionBody),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: qk.alert(alertId) });
      await queryClient.invalidateQueries({ queryKey: ["alerts"] });
      setAccion("");
      setAdjunto("");
      toast.success("Acción registrada.");
    },
    onError: (error: unknown) => toast.error(mensajeDeError(error)),
  });

  const etiquetaDeAccion = (clave: string) =>
    catalogo.data?.items.find((i) => i.action === clave)?.label ?? clave;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle>Acciones</CardTitle>
        <Button type="button" size="sm" disabled={!accion} onClick={() => setAbierto(true)}>
          Registrar acción
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="accion-select">Acción del catálogo</Label>
            <Select value={accion} onValueChange={setAccion}>
              <SelectTrigger id="accion-select" className="w-full">
                <SelectValue placeholder="Elige una acción" />
              </SelectTrigger>
              <SelectContent>
                {(catalogo.data?.items ?? []).map((item) => (
                  <SelectItem key={item.action} value={item.action}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="accion-adjunto">Adjunto (ruta de texto, opcional)</Label>
            <Input
              id="accion-adjunto"
              value={adjunto}
              onChange={(e) => setAdjunto(e.target.value)}
              placeholder="C:\ruta\al\fichero.pdf"
            />
          </div>
        </div>
        <div className="flex flex-col gap-2">
          {acciones.length === 0 ? (
            <p className="text-sm text-muted-foreground">Todavía no se ha registrado ninguna acción.</p>
          ) : (
            acciones.map((a) => (
              <div key={a.id} className="rounded-md border border-border p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold">{etiquetaDeAccion(a.action)}</span>
                  <span className="text-xs text-tertiary">{formatoFecha(a.ts)}</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  {a.actor}
                  {a.role ? ` · ${ETIQUETA_ROL[a.role as Rol] ?? a.role}` : ""}
                  {a.attachment_path ? ` · adjunto: ${a.attachment_path}` : ""}
                </p>
                <p>{a.motivo}</p>
              </div>
            ))
          )}
        </div>
      </CardContent>
      <MotivoDialog
        open={abierto}
        onOpenChange={setAbierto}
        titulo={`Registrar acción: ${etiquetaDeAccion(accion)}`}
        etiquetaConfirmar="Registrar"
        ejemplo={EJEMPLO_MOTIVO.accionAlerta}
        onConfirm={async (cuerpo) => {
          await mutacion.mutateAsync(cuerpo);
        }}
      />
    </Card>
  );
}

export default Acciones;
