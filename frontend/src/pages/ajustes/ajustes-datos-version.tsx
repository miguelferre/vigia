/**
 * Bloques «Carpeta de datos» y «Versión» de `/ajustes`:
 * solo lectura, fuera de `cliente`. Partido de `index.tsx` por tamaño.
 */

import { CopyIcon } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Health, Settings } from "@/api/types";

export interface AjustesDatosVersionProps {
  settings: Settings;
  health?: Health;
}

export function AjustesDatosVersion({ settings, health }: AjustesDatosVersionProps) {
  return (
    <>
      <Card id="datos" className="scroll-mt-20">
        <CardHeader>
          <CardTitle>Carpeta de datos</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <code className="max-w-full rounded border border-border bg-muted px-2 py-1 text-sm [overflow-wrap:anywhere]">
              {settings.data_dir}
            </code>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                void navigator.clipboard.writeText(settings.data_dir);
                toast.success("Ruta copiada.");
              }}
            >
              <CopyIcon /> Copiar
            </Button>
          </div>
          <p className="text-sm text-muted-foreground">
            No se puede cambiar desde aquí. Se cambia con --data-dir o la variable VIGIA_HOME.
          </p>
        </CardContent>
      </Card>

      <Card id="version" className="scroll-mt-20">
        <CardHeader>
          <CardTitle>Versión</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-1 text-sm text-muted-foreground">
          <p>Vigía {health?.version ?? "…"}</p>
          <p>Python {health?.python ?? "…"}</p>
          <p>Esquema {health?.schema_version ?? "…"}</p>
          {/* `puerto` es el del próximo arranque (`PATCH /settings`); el actual lo da `/health`. */}
          <p>
            Puerto {health?.port ?? settings.puerto}
            {health?.port != null && health.port !== settings.puerto ? ` (configurado para el próximo arranque: ${settings.puerto})` : ""}
          </p>
        </CardContent>
      </Card>
    </>
  );
}
