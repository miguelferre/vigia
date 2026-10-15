/**
 * `/modelos` (y `/`): rejilla de tarjetas de despliegue.
 *
 * Una sola petición (`GET /projects?summary=true`): cada fila ya
 * trae `summary` (peor estado, alertas abiertas por severidad, última
 * evaluación, inicio de monitorización, versión activa), así que no hace
 * falta pedir el detalle fila a fila (`useQueries` + `LIMITE_DETALLE` de la
 * versión anterior). Tarjeta y diálogo de creación, en ficheros
 * aparte para no superar 9 KB.
 */

import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { PlusIcon } from "lucide-react";
import { toast } from "sonner";

import { api, mensajeDeError } from "@/api/client";
import { qk, useProjectsSummary } from "@/api/queries";
import type { Project, ProjectCreate } from "@/api/types";
import { useSession } from "@/session/session";
import { ErrorDeConsulta, PageHeader } from "@/components/vigia";
import { useTitulo } from "@/hooks/useTitulo";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { leerAccionDemo, notificarDemo } from "@/components/vigia/DemoGuiada/contrato";

import { NuevoModeloDialog } from "./nuevo-modelo-dialog";
import { PortadaEmpezar } from "./portada-empezar";
import { TarjetaModelo } from "./tarjeta-modelo";

export default function ModelosIndex() {
  useTitulo("Modelos");
  const navigate = useNavigate();
  const { setProjectId } = useSession();
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useProjectsSummary();
  const proyectos = data?.items ?? [];
  const [searchParams, setSearchParams] = useSearchParams();

  // `?demo=crear` (contrato.ts): el diálogo se abre solo al montar. Se lee
  // una vez al inicializar el estado, no en un efecto (no hace falta que
  // reaccione a cambios posteriores de la URL en esta misma pantalla).
  // `?alta=1`: lo mismo, sin precarga, desde el estado vacío
  // de las demás pantallas.
  const [abierto, setAbierto] = useState(
    () => leerAccionDemo(searchParams.toString()) === "crear" || searchParams.get("alta") === "1",
  );
  const precargaDemo = leerAccionDemo(searchParams.toString()) === "crear";

  const limpiarDemoUrl = () => {
    if (searchParams.has("demo") || searchParams.has("alta")) {
      const next = new URLSearchParams(searchParams);
      next.delete("demo");
      next.delete("alta");
      setSearchParams(next, { replace: true });
    }
  };

  const abrirCuadro = (p: Project) => {
    if (p.id === null) return;
    setProjectId(p.id);
    navigate("/cuadro");
  };

  const crear = async (cuerpo: ProjectCreate) => {
    try {
      const proyecto = await api.post<Project>("/projects", cuerpo);
      await queryClient.invalidateQueries({ queryKey: qk.projectsSummary() });
      // El detalle del proyecto nuevo puede estar en caché con un 404: la barra
      // lateral lo pidió con el `projectId` que la sesión recordaba de una base
      // anterior y el id se ha reutilizado. Sin esto,
      // `/modelos/:id` enseñaba «Despliegue no
      // encontrado» hasta recargar.
      if (proyecto.id !== null) await queryClient.invalidateQueries({ queryKey: qk.project(proyecto.id) });
      toast.success(`Despliegue «${proyecto.name}» creado`);
      setAbierto(false);
      limpiarDemoUrl();
      // Sin demo activa, avisar no tiene efecto (contrato.ts).
      if (proyecto.id !== null) notificarDemo({ tipo: "modelo-creado", projectId: proyecto.id });
    } catch (error) {
      toast.error(mensajeDeError(error));
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        titulo="Modelos"
        descripcion="Despliegues vigilados: estado de cada monitor, última evaluación y alertas abiertas. Pulsa una luz para ver el detalle."
        acciones={
          <Button id="crear-modelo" className="scroll-mt-20" onClick={() => setAbierto(true)}>
            <PlusIcon className="size-4" aria-hidden="true" />
            Crear modelo
          </Button>
        }
      />
      {isError ? (
        <ErrorDeConsulta que="los modelos" error={error} onReintentar={() => void refetch()} />
      ) : !isLoading && proyectos.length === 0 ? (
        <PortadaEmpezar onAlta={() => setAbierto(true)} />
      ) : (
        <div
          className="grid grid-cols-1 gap-4 @md:grid-cols-2 @4xl:grid-cols-3"
          data-loading={isLoading || undefined}
        >
          {proyectos.map((p) => (
            <TarjetaModelo key={p.id} proyecto={p} onAbrir={abrirCuadro} />
          ))}
        </div>
      )}

      <Dialog
        open={abierto}
        onOpenChange={(o) => {
          setAbierto(o);
          if (!o) limpiarDemoUrl();
        }}
      >
        <NuevoModeloDialog
          onCrear={crear}
          precargaDemo={precargaDemo}
          nombresExistentes={proyectos.map((p) => p.name)}
        />
      </Dialog>
    </div>
  );
}
