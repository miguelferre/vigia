/**
 * `/modelos/:id`: cabecera del proyecto y pestañas (versiones, datos,
 * monitores, configuración). Cada pestaña vive en su propio fichero.
 */

import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router";

import { Link } from "react-router";

import { useProject } from "@/api/queries";
import { EmptyState, PageHeader } from "@/components/vigia";
import { useTitulo } from "@/hooks/useTitulo";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCan, useSession } from "@/session/session";

import VersionesTab from "./versiones";
import CompararTab from "./comparar";
import DatosTab from "./datos";
import MonitoresTab from "./monitores";
import ConfiguracionTab from "./configuracion";
import UmbralesTab from "./alta-umbrales";
import { ETIQUETA_DOMINIO } from "./etiquetas";

const PESTANAS = ["versiones", "comparar", "datos", "monitores", "umbrales", "configuracion"] as const;
type Pestana = (typeof PESTANAS)[number];

/** Ancla (`#pestana`) a pestaña activa: la usa el onboarding para llegar
 * directo a una pestaña concreta. Sin ancla o con una que no corresponde,
 * la pestaña por defecto sigue siendo "versiones". */
function pestanaDesdeHash(hash: string, puedeConfig: boolean, hayComparar: boolean): Pestana {
  const candidata = hash.replace(/^#/, "");
  // `#subir-datos` (botón «Subir dataset» y `?demo=subir`, contrato.ts) abre
  // la pestaña Datos igual que si el hash fuera `#datos`.
  if (candidata === "subir-datos") return "datos";
  const valida = (PESTANAS as readonly string[]).includes(candidata);
  const restringida = candidata === "configuracion" || candidata === "umbrales";
  // «Comparar» solo existe con dos versiones o más.
  if (candidata === "comparar" && !hayComparar) return "versiones";
  if (valida && (!restringida || puedeConfig)) return candidata as Pestana;
  return "versiones";
}

export default function ModeloDetalle() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const projectId = id ? Number(id) : null;
  const { setProjectId } = useSession();
  const puedeConfig = useCan("config");
  const { data: proyecto, isLoading, isFetching, isError, fetchStatus } = useProject(projectId);
  useTitulo(proyecto?.name ?? "Modelos");
  const hayComparar = (proyecto?.versions.length ?? 0) >= 2;
  const [pestana, setPestana] = useState<Pestana>(() =>
    pestanaDesdeHash(location.hash, puedeConfig, hayComparar),
  );
  // Ajuste de estado durante el render (no en un efecto): si el hash o el
  // permiso cambian, la pestaña se recalcula antes de pintar, sin el
  // parpadeo de un `useEffect` posterior.
  // `hayComparar` solo entra en la clave con `#comparar` (carga con el
  // proyecto aún sin llegar): si otro cliente crea la segunda versión, quien
  // está en otra pestaña no vuelve a «Versiones».
  const claveHash = `${location.hash}|${puedeConfig}|${location.hash === "#comparar" && hayComparar}`;
  const [claveHashAplicada, setClaveHashAplicada] = useState(claveHash);
  if (claveHash !== claveHashAplicada) {
    setClaveHashAplicada(claveHash);
    setPestana(pestanaDesdeHash(location.hash, puedeConfig, hayComparar));
  }
  // Si «Comparar» deja de existir con ella abierta, se degrada a «Versiones».
  if (pestana === "comparar" && !hayComparar) setPestana("versiones");

  useEffect(() => {
    if (projectId !== null && !Number.isNaN(projectId)) setProjectId(projectId);
  }, [projectId, setProjectId]);

  if (projectId === null || Number.isNaN(projectId)) return null;

  // Con un error anterior en caché (el detalle pedido con un id que ya no
  // existía) la primera visita vuelve a pedirlo: mientras llega, no se da por
  // no encontrado. `fetchStatus
  // === "paused"` (TanStack pausa la petición con la pestaña oculta o sin
  // red) también deja `isFetching` en `false` sin que la consulta haya
  // terminado de verdad: no cuenta como no encontrado.
  if (!isLoading && !isFetching && fetchStatus !== "paused" && (isError || !proyecto)) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          titulo="Despliegue no encontrado"
          migas={[{ etiqueta: "Modelos", a: "/modelos" }, { etiqueta: String(projectId) }]}
        />
        <EmptyState
          titulo="Este despliegue no existe o se ha borrado"
          descripcion="Vuelve al listado de modelos para elegir otro despliegue."
          accion={
            <Button asChild size="sm" variant="outline">
              <Link to="/modelos">Ir a Modelos</Link>
            </Button>
          }
        />
      </div>
    );
  }

  const activa = proyecto?.versions.find((v) => v.id === proyecto.active_version_id);

  return (
    <div className="flex flex-col gap-6" data-loading={isLoading || undefined}>
      <PageHeader
        titulo={proyecto?.name ?? (isLoading ? "Cargando…" : `Despliegue ${projectId}`)}
        migas={[
          { etiqueta: "Modelos", a: "/modelos" },
          { etiqueta: proyecto?.name ?? String(projectId) },
        ]}
        descripcion={
          proyecto ? (
            <span className="flex flex-wrap items-center gap-2">
              Dominio {ETIQUETA_DOMINIO[proyecto.domain] ?? proyecto.domain}{" "}
              {activa ? (
                <>
                  · modelo activo <strong>{activa.label}</strong>
                </>
              ) : (
                "· sin modelo activo"
              )}
            </span>
          ) : null
        }
      />
      <Tabs value={pestana} onValueChange={(v) => setPestana(v as Pestana)}>
        {/* Con las cinco pestañas (rol con configuración) la lista
            medía 415 px a 375 y ensanchaba toda la página; ahora hace scroll
            dentro de este contenedor. */}
        <div className="max-w-full overflow-x-auto">
          <TabsList>
            <TabsTrigger value="versiones">Versiones</TabsTrigger>
            {hayComparar ? <TabsTrigger value="comparar">Comparar</TabsTrigger> : null}
            <TabsTrigger value="datos">Datos</TabsTrigger>
            <TabsTrigger value="monitores">Monitores</TabsTrigger>
            {puedeConfig ? <TabsTrigger value="umbrales">Umbrales</TabsTrigger> : null}
            {puedeConfig ? <TabsTrigger value="configuracion">Configuración</TabsTrigger> : null}
          </TabsList>
        </div>
        <TabsContent value="versiones">
          <VersionesTab projectId={projectId} />
        </TabsContent>
        {hayComparar ? (
          <TabsContent value="comparar">
            <CompararTab projectId={projectId} />
          </TabsContent>
        ) : null}
        <TabsContent value="datos">
          <DatosTab projectId={projectId} />
        </TabsContent>
        <TabsContent value="monitores">
          <MonitoresTab projectId={projectId} />
        </TabsContent>
        {puedeConfig ? (
          <TabsContent value="umbrales">
            <UmbralesTab projectId={projectId} />
          </TabsContent>
        ) : null}
        {puedeConfig ? (
          <TabsContent value="configuracion">
            <ConfiguracionTab projectId={projectId} onBorrado={() => navigate("/modelos")} />
          </TabsContent>
        ) : null}
      </Tabs>
    </div>
  );
}
