/**
 * Raíz de la aplicación: proveedores, rutas y armazón.
 *
 * Una ruta por pantalla, cargada con `React.lazy` para que cada una vaya en su
 * propio chunk. Las pantallas viven en `src/pages/<carpeta>` y se registran aquí.
 *
 * `DemoGuiadaProvider` va dentro de `BrowserRouter` porque
 * navega al destino de cada paso; `/onboarding` redirige a `/ayuda#guia`
 * `/monitores/:tipo` se remonta cuando cambia `?metrica=`: la pantalla lee ese parámetro una vez al montar, y la demo guiada
 * pasa de `/monitores/equidad` a `/monitores/equidad?metrica=...` sin cambiar
 * de ruta.
 */

import { lazy } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useSearchParams } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { DemoGuiadaProvider } from "@/components/vigia/DemoGuiada/Provider";
import { EmptyState } from "@/components/vigia/EmptyState";
import { ModoPresentacionProvider } from "@/components/vigia/ModoPresentacion";
import { PageHeader } from "@/components/vigia/PageHeader";
import { AppShell } from "@/layout/AppShell";
import { STALE_MS } from "@/api/queries";
import { SessionProvider } from "@/session/session";
import { ThemeProvider } from "@/themes/theme";

const Dashboard = lazy(() => import("@/pages/dashboard/index"));
const Diario = lazy(() => import("@/pages/diario/index"));
const Modelos = lazy(() => import("@/pages/modelos/index"));
const ModeloDetalle = lazy(() => import("@/pages/modelos/detalle"));
const Datos = lazy(() => import("@/pages/datos/index"));
const Monitores = lazy(() => import("@/pages/monitores/index"));
const Alertas = lazy(() => import("@/pages/alertas/index"));
const AlertaDetalle = lazy(() => import("@/pages/alertas/detalle"));
const Explicabilidad = lazy(() => import("@/pages/explicabilidad/index"));
// las cuatro pantallas nuevas, entre explicabilidad y demo.
const CapaHumana = lazy(() => import("@/pages/capa-humana/index"));
const Auditoria = lazy(() => import("@/pages/auditoria/index"));
const Riesgos = lazy(() => import("@/pages/riesgos/index"));
const Ajustes = lazy(() => import("@/pages/ajustes/index"));
const Demo = lazy(() => import("@/pages/demo/index"));
const Ayuda = lazy(() => import("@/pages/ayuda/index"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: STALE_MS,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

/** Remonta la pantalla de monitores al cambiar `?metrica=` (ver docstring). */
function MonitoresPorMetrica() {
  const [searchParams] = useSearchParams();
  return <Monitores key={searchParams.get("metrica") ?? ""} />;
}

function NoEncontrado() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader titulo="Página no encontrada" />
      <EmptyState
        titulo="Esa ruta no existe"
        descripcion="Comprueba la dirección o vuelve a Modelos."
        accion={
          <Button asChild>
            <Link to="/">Ir a Modelos</Link>
          </Button>
        }
      />
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <SessionProvider>
          <ModoPresentacionProvider>
            <BrowserRouter>
              <DemoGuiadaProvider>
                <Routes>
                  <Route element={<AppShell />}>
                    <Route index element={<Modelos />} />
                    <Route path="cuadro" element={<Dashboard />} />
                    <Route path="diario" element={<Diario />} />
                    <Route path="modelos" element={<Modelos />} />
                    <Route path="modelos/:id" element={<ModeloDetalle />} />
                    <Route path="datos/:batch" element={<Datos />} />
                    <Route path="monitores/:tipo" element={<MonitoresPorMetrica />} />
                    <Route path="alertas" element={<Alertas />} />
                    <Route path="alertas/:id" element={<AlertaDetalle />} />
                    <Route path="explicabilidad" element={<Explicabilidad />} />
                    <Route path="capa-humana" element={<CapaHumana />} />
                    <Route path="auditoria" element={<Auditoria />} />
                    <Route path="riesgos" element={<Riesgos />} />
                    <Route path="ajustes" element={<Ajustes />} />
                    <Route path="demo" element={<Demo />} />
                    <Route path="onboarding" element={<Navigate to="/ayuda#guia" replace />} />
                    <Route path="ayuda" element={<Ayuda />} />
                    <Route path="*" element={<NoEncontrado />} />
                  </Route>
                </Routes>
              </DemoGuiadaProvider>
            </BrowserRouter>
            <Toaster />
          </ModoPresentacionProvider>
        </SessionProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
