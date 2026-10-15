/**
 * Panel asistente: botón de cabecera con el rastro en vivo del
 * carril `agente` del diario (eventos que escriben las tools del servidor MCP),
 * agrupado por `correlation_id` y con enlace al objeto de cada grupo. Enseña,
 * no conversa.
 *
 * Se despliega solo una vez, al llegar el primer evento `agente` de la
 * pestaña (si `!visto`); se pliega y reabre como cualquier `Popover`, y el
 * botón de cabecera lo reabre en cualquier momento. Icono elegido: `BotIcon`
 * (asistente, no persona ni chispa) a trazo 1,5, fuera del render por
 * llamada (patrón `lib/iconos.ts`).
 */

import { useEffect, useState } from "react";
import { BotIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useDemoGuiada } from "@/components/vigia/DemoGuiada/contexto";

import { ListaEventosAgente } from "./ListaEventosAgente";
import { useEventosAgente } from "./useEventosAgente";

const VENTANA_MIN = 30;

// Con la demo guiada desplegada (panel acoplado en `lg`, `AppShell` marca
// `<html data-demo-activa>`), el panel de la demo ocupa 20rem (320px) a la
// derecha. A diferencia de `AlertaPanel.tsx`/`configuracion.tsx` (hojas
// `position: fixed` propio, donde una clase `right-80` sí mueve el borde),
// el `PopoverContent` de Radix se posiciona con `transform` sobre un
// wrapper `position: fixed; left: 0; top: 0`: la propiedad CSS `right` no
// tiene efecto ahí (verificado con playwright: la clase era inerte, mismo
// `boundingBox` con y sin `data-demo-activa`). `collisionPadding` tampoco
// sirve: con `avoidCollisions` activo, floating-ui limita el `shift` al
// ancho del propio disparador (verificado: solo 42px de movimiento, muy
// por debajo de los 320px del panel). Con la demo activa se usa
// `alignOffset` fijo y se apaga `avoidCollisions` (nada que colisionar: el
// panel de la demo no es un elemento de la colisión de Radix, es contenido
// aparte) para que el desplazamiento se aplique entero (verificado: el
// `boundingBox` se mueve los 320px exactos). Se lee de `useDemoGuiada()`
// (mismo estado que fija el atributo en AppShell), no del DOM, para que
// sea reactivo sin observer.
const ANCHO_PANEL_DEMO_PX = 320;
// `lg` de Tailwind (1024px): por debajo, el panel de la demo es una hoja
// inferior y no hay nada de lo que apartarse a la derecha.
const CONSULTA_LG = "(min-width: 1024px)";

export function PanelAsistente() {
  // El despliegue automático y la poda viven en el hook: nacen del listener
  // SSE y de esta apertura, nunca de un efecto que escriba estado.
  const { grupos, visto, abierto, setAbierto } = useEventosAgente(VENTANA_MIN);
  const demo = useDemoGuiada();
  const [esLg, setEsLg] = useState(
    () => typeof window !== "undefined" && window.matchMedia(CONSULTA_LG).matches
  );
  useEffect(() => {
    const mql = window.matchMedia(CONSULTA_LG);
    const escuchar = () => setEsLg(mql.matches);
    mql.addEventListener("change", escuchar);
    return () => mql.removeEventListener("change", escuchar);
  }, []);
  const panelDemoDesplegado = demo.activa && !demo.plegado && esLg;
  const total = grupos.reduce((n, g) => n + g.eventos.length, 0);

  return (
    <Popover open={abierto} onOpenChange={setAbierto}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="relative gap-2"
          aria-label={`Asistente: ${total} acciones de agentes`}
        >
          <BotIcon className="size-4" strokeWidth={1.5} aria-hidden="true" />
          {!visto && total > 0 ? (
            <span
              className="absolute top-1 right-1 size-2 rounded-full"
              style={{ background: "var(--chart-1)" }}
              aria-hidden="true"
            />
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-96"
        alignOffset={panelDemoDesplegado ? ANCHO_PANEL_DEMO_PX : undefined}
        avoidCollisions={!panelDemoDesplegado}
      >
        <div className="mb-2 flex flex-col gap-0.5">
          <p className="text-sm font-semibold">Acciones de agentes de IA</p>
          <p className="text-xs text-tertiary">Últimos {VENTANA_MIN} minutos</p>
        </div>
        <ListaEventosAgente grupos={grupos} onNavegar={() => setAbierto(false)} />
      </PopoverContent>
    </Popover>
  );
}
