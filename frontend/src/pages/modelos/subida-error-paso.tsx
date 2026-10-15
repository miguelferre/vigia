/**
 * Error de un paso del asistente de subida: se queda a
 * la vista, con su botón de cierre, hasta que el usuario lo cierra, cambia
 * de fichero o repite el paso con éxito. Antes salía como aviso emergente y
 * desaparecía antes de leerlo (el texto dice qué hacer con un lote ilegible).
 */

import { TriangleAlertIcon, XIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

interface Props {
  error: string | null;
  onCerrar: () => void;
}

export function ErrorPasoSubida({ error, onCerrar }: Props) {
  if (!error) return null;
  return (
    <Alert variant="destructive" data-testid="error-paso-subida">
      <TriangleAlertIcon aria-hidden="true" />
      <AlertTitle className="flex items-center justify-between gap-2">
        No se ha podido continuar
        <Button type="button" variant="ghost" size="icon" aria-label="Cerrar el error" onClick={onCerrar}>
          <XIcon className="size-4" aria-hidden="true" />
        </Button>
      </AlertTitle>
      <AlertDescription>{error}</AlertDescription>
    </Alert>
  );
}
