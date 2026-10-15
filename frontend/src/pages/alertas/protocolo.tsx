/**
 * Texto libre del protocolo del monitor: el bloque
 * principal de protocolo es `ProtocoloHitos` (cinco pasos con estado real);
 * este componente pasa a un desplegable al final de esa sección, para quien
 * quiera el texto original que configuró el monitor.
 *
 * Se configura una sola vez en el monitor y cada alerta hereda el texto en
 * el momento en que se abre (`alerting.py`, `_sync_one`); aquí solo se lee, con
 * enlace al monitor para editarlo. `PUT /alerts/{id}/protocol` se mantiene
 * en la API (para el MCP y para no perder historial): esta
 * pantalla no ofrece edición.
 */

import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { useTextosPantalla } from "@/api/queries-contenido";

const EXPLICACION_POR_DEFECTO =
  "Texto de protocolo configurado en el monitor en el momento en que se abrió esta alerta. " +
  "Se edita en la configuración del monitor; aquí solo se lee.";

export interface ProtocoloProps {
  protocoloMd: string;
  /** Segmento de `/monitores/:tipo` del monitor que la generó; sin enlace si no se conoce. */
  rutaMonitor?: string;
}

export function Protocolo({ protocoloMd, rutaMonitor }: ProtocoloProps) {
  const textos = useTextosPantalla();
  const explicacion = textos.data?.alertas?.protocolo_que_es ?? EXPLICACION_POR_DEFECTO;

  return (
    // El ancla `#protocolo` de la demo (paso 23) vive ahora en el
    // `<details>` exterior de `detalle.tsx`, que envuelve los hitos y este
    // bloque de texto libre: aquí ya no hace falta `id`.
    <details className="text-md">
      <summary className="cursor-pointer font-semibold text-tertiary select-none">
        Protocolo del monitor (texto)
      </summary>
      <div className="mt-2 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-tertiary">{explicacion}</p>
          {rutaMonitor ? (
            <Button asChild type="button" variant="outline" size="sm" className="flex-none">
              <Link to={`/monitores/${rutaMonitor}`}>Editar en el monitor</Link>
            </Button>
          ) : null}
        </div>
        <div className="rounded-md border border-border bg-muted/40 p-3 whitespace-pre-wrap">
          {protocoloMd.trim().length > 0 ? protocoloMd : "Sin protocolo definido."}
        </div>
      </div>
    </details>
  );
}

export default Protocolo;
