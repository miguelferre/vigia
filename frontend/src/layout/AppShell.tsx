/**
 * Armazón de la aplicación.
 *
 * Barra lateral colapsable a partir de 1024 px y en `Sheet` por debajo;
 * cabecera con selector de proyecto, trabajos en curso, estado de la conexión
 * SSE, tema y sesión. El contenido de cada ruta entra por `<Outlet>`.
 *
 * el panel de la demo guiada (`PanelDemo`) va acoplado a la
 * derecha del `<main>` en `lg` y como hoja inferior por debajo, fuera del
 * `ErrorBoundary` de la ruta para que un fallo de pantalla no se lo lleve, y
 * visible también en modo presentación.
 *
 * la marca lleva `LogoVigia` en la barra y en la hoja móvil, y
 * `<main>` es un contenedor (`@container`, Tailwind v4) para que las rejillas
 * de tarjetas se plieguen por el ancho que les queda con el panel de la demo
 * abierto, no por el de la ventana.
 *
 * el panel asistente (`PanelAsistente`) va en la cabecera,
 * junto a `JobsBadge`, visible en toda ruta; docking distinto del de la demo.
 */

import { Suspense, useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router";
import { MenuIcon, PanelLeftIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useDemoGuiada } from "@/components/vigia/DemoGuiada/contexto";
import { PanelDemo } from "@/components/vigia/DemoGuiada/PanelDemo";
import { ErrorBoundary } from "@/components/vigia/ErrorBoundary";
import { LogoVigia } from "@/components/vigia/LogoVigia";
import { useModoPresentacion } from "@/components/vigia/ModoPresentacion";
import { PanelAsistente } from "@/components/vigia/PanelAsistente/PanelAsistente";
import { JobsBadge } from "@/layout/JobsBadge";
import { ProjectSelector } from "@/layout/ProjectSelector";
import { SessionMenu } from "@/layout/SessionMenu";
import { Sidebar } from "@/layout/Sidebar";
import { ThemeMenu } from "@/layout/ThemeMenu";
import { useEventStream } from "@/realtime/events";
import type { EstadoConexion } from "@/realtime/events";
import { cn } from "@/lib/utils";

export function AppShell() {
  const [colapsada, setColapsada] = useState(false);
  const [movilAbierta, setMovilAbierta] = useState(false);
  const { estado } = useEventStream();
  const location = useLocation();
  const { activo: presentacion } = useModoPresentacion();
  const demo = useDemoGuiada();
  // Con la hoja inferior de la demo abierta (por debajo de `lg`) el contenido
  // deja sitio para que el pie de la pantalla no quede tapado.
  const hojaDemo = demo.activa && !demo.plegado;
  // Con el panel de la demo desplegado, `<html>` lleva `data-demo-activa`:
  // las hojas laterales que se montan en un portal (el panel de alerta) lo
  // leen para apartarse del panel en `lg` (la hoja lo
  // tapaba). Un atributo en la raíz, y no en este árbol, porque el portal
  // vive fuera de él.
  useEffect(() => {
    if (hojaDemo) document.documentElement.setAttribute("data-demo-activa", "true");
    else document.documentElement.removeAttribute("data-demo-activa");
    return () => document.documentElement.removeAttribute("data-demo-activa");
  }, [hojaDemo]);
  // `/` y `/modelos` son la rejilla de modelos; el selector de
  // proyecto de la cabecera no pinta ahí, el clic en la tarjeta ya fija uno.
  const ocultarSelector = location.pathname === "/" || location.pathname === "/modelos";

  return (
    <div
      className={cn(
        "flex min-h-screen bg-background text-foreground",
        presentacion ? "text-[1.0625rem] leading-relaxed" : null,
      )}
      data-presentacion={presentacion ? "true" : undefined}
    >
      <aside
        className={cn(
          "hidden shrink-0 border-r border-border bg-card lg:block",
          colapsada ? "w-16" : "w-60",
          presentacion ? "lg:hidden" : null,
        )}
      >
        <div className="flex h-14 items-center gap-2 border-b border-border px-3">
          <Link to="/" className="flex items-center gap-2" aria-label="Vigía, portada">
            <LogoVigia size={20} decorativo className="shrink-0 text-[var(--primary)]" />
            {!colapsada ? (
              <span className="font-display text-base font-semibold tracking-[-0.15px]">Vigía</span>
            ) : null}
          </Link>
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto"
            aria-label={colapsada ? "Desplegar la barra lateral" : "Plegar la barra lateral"}
            onClick={() => setColapsada((c) => !c)}
          >
            <PanelLeftIcon className="size-4" aria-hidden="true" />
          </Button>
        </div>
        <Sidebar colapsada={colapsada} />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header
          className={cn(
            "sticky top-0 z-10 flex h-auto min-h-14 flex-wrap items-center gap-2 border-b border-border bg-card px-3 py-2",
            presentacion ? "hidden" : null,
          )}
        >
          <Sheet open={movilAbierta} onOpenChange={setMovilAbierta}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Menú">
                <MenuIcon className="size-4" aria-hidden="true" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 p-0">
              <SheetTitle className="flex items-center gap-2 border-b border-border px-4 py-3 font-display text-base font-semibold tracking-[-0.15px]">
                <LogoVigia size={20} decorativo className="shrink-0 text-[var(--primary)]" />
                Vigía
              </SheetTitle>
              <Sidebar colapsada={false} onNavegar={() => setMovilAbierta(false)} />
            </SheetContent>
          </Sheet>

          <div className="min-w-0 flex-1">{!ocultarSelector ? <ProjectSelector /> : null}</div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <IndicadorConexion estado={estado} />
            <JobsBadge />
            <PanelAsistente />
            <ThemeMenu />
            <SessionMenu />
          </div>
        </header>

        <div className="flex min-w-0 flex-1 items-stretch">
          <main className={cn("@container min-w-0 flex-1 px-4 py-6 lg:px-6", hojaDemo ? "pb-[45vh] lg:pb-6" : null)}>
            <ErrorBoundary key={location.pathname}>
              <Suspense fallback={<CargandoPantalla />}>
                <Outlet />
              </Suspense>
            </ErrorBoundary>
          </main>
          <PanelDemo />
        </div>

        {!presentacion ? (
          <footer className="border-t border-border px-4 py-3 text-xs text-tertiary lg:px-6">
            Vigía · vigilancia de modelos
          </footer>
        ) : null}
      </div>
    </div>
  );
}

const TEXTO_CONEXION: Record<EstadoConexion, string> = {
  conectando: "Conectando con el diario en vivo",
  conectado: "Diario en vivo conectado",
  desconectado: "Diario en vivo desconectado",
};

/** Punto de estado en vez de icono de wifi; el interruptor «Seguir en
 * vivo» del diario (`pages/diario/Filtros.tsx`) es otra cosa. */
const TEXTO_BREVE: Record<EstadoConexion, string> = {
  conectando: "Conectando…",
  conectado: "Conectado",
  desconectado: "Sin conexión",
};

const TOKEN_PUNTO: Record<EstadoConexion, string> = {
  conectando: "var(--state-nodata)",
  conectado: "var(--state-ok)",
  desconectado: "var(--state-nodata)",
};

function IndicadorConexion({ estado }: { estado: EstadoConexion }) {
  const conectado = estado === "conectado";
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs"
      title={TEXTO_CONEXION[estado]}
      data-sse={estado}
    >
      <span
        className={cn("inline-block size-2 rounded-full", conectado && "animate-pulse")}
        style={{ background: TOKEN_PUNTO[estado] }}
        aria-hidden="true"
      />
      <span className="hidden sm:inline">{TEXTO_BREVE[estado]}</span>
      <span className="sr-only">{TEXTO_CONEXION[estado]}</span>
    </span>
  );
}

function CargandoPantalla() {
  return (
    <div className="flex flex-col gap-4" data-loading="true">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}
