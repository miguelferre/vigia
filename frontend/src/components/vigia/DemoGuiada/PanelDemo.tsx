/**
 * Panel acoplado de la demo guiada: en `lg` es un
 * `aside` a la derecha del contenido (unos 20 rem, borde izquierdo, pegado
 * bajo la cabecera y con desplazamiento propio); por debajo, una hoja
 * inferior fija. Se pliega a una pastilla «Demo · paso N de 29» que lo
 * despliega. Persiste al navegar porque lo monta `AppShell`, fuera del
 * `ErrorBoundary` del `Outlet`, y se ve también en modo presentación
 * (quien presenta hace clic en él). Sin demo activa no pinta nada. Al
 * cambiar de paso el cuerpo vuelve arriba (con 26 pasos, el texto del
 * anterior podía dejar el nuevo título fuera de la vista). Numeración de
 * 1 a 29: «paso» cuenta desde 0, se muestra `paso + 1`.
 */

import { useEffect, useRef } from "react";
import { ChevronDownIcon, ChevronUpIcon, XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useModoPresentacion } from "@/components/vigia/ModoPresentacion";
import { cn } from "@/lib/utils";

import { BotonReiniciarDemo } from "./BotonReiniciarDemo";
import { ContenidoPanel } from "./ContenidoPanel";
import { useDemoGuiada } from "./contexto";

export function PanelDemo() {
  const { activa, plegado, plegar, cerrar, paso, pasos } = useDemoGuiada();
  const { activo: presentacion } = useModoPresentacion();
  const cuerpo = useRef<HTMLDivElement>(null);
  useEffect(() => {
    cuerpo.current?.scrollTo({ top: 0 });
  }, [paso]);
  if (!activa) return null;

  if (plegado) {
    return (
      <button
        type="button"
        onClick={() => plegar(false)}
        className={cn(
          "fixed right-4 bottom-4 z-20 inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-semibold shadow-md",
          "hover:bg-muted",
        )}
        aria-expanded={false}
        data-panel-demo="plegado"
      >
        <span className="inline-block size-2 rounded-full" style={{ background: "var(--chip-active)" }} aria-hidden="true" />
        Demo · paso {paso + 1} de {pasos.length}
        <ChevronUpIcon className="size-4" aria-hidden="true" />
      </button>
    );
  }

  return (
    <aside
      className={cn(
        "fixed inset-x-0 bottom-0 z-20 flex max-h-[60vh] flex-col border-t border-border bg-card shadow-lg",
        "lg:sticky lg:inset-x-auto lg:z-auto lg:max-h-none lg:w-80 lg:shrink-0 lg:self-start lg:border-t-0 lg:border-l lg:shadow-none",
        // Sin cabecera (modo presentación) el panel ocupa la altura entera.
        presentacion ? "lg:top-0 lg:h-screen" : "lg:top-14 lg:h-[calc(100vh-3.5rem)]",
      )}
      aria-label="Demo guiada"
      data-panel-demo="abierto"
    >
      <div className="flex h-12 shrink-0 items-center gap-1 border-b border-border px-3">
        <span className="font-display text-sm font-semibold">Demo guiada</span>
        <div className="ml-auto flex items-center gap-0.5">
          <BotonReiniciarDemo variant="ghost" size="icon" />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Plegar el panel de la demo"
            title="Plegar"
            onClick={() => plegar(true)}
          >
            <ChevronDownIcon className="size-4" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Cerrar el panel de la demo"
            title="Cerrar (la demo se puede continuar desde /demo)"
            onClick={cerrar}
          >
            <XIcon className="size-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
      <div ref={cuerpo} className="min-h-0 flex-1 overflow-y-auto">
        <ContenidoPanel />
      </div>
    </aside>
  );
}
