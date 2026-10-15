/** Bloque «Configuración avanzada (JSON)» de la hoja «Configurar monitor» (partido de `configuracion.tsx` por tamaño). */

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Textarea } from "@/components/ui/textarea";

export function ConfiguracionAvanzada({
  texto,
  onCambiar,
  error,
}: {
  texto: string;
  onCambiar: (texto: string) => void;
  error: string | null;
}) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm text-muted-foreground">Configuración avanzada (JSON)</h3>
      <Textarea value={texto} rows={6} className="font-mono text-xs" onChange={(e) => onCambiar(e.target.value)} />
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
