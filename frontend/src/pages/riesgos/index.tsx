/**
 * Riesgos (ruta `/riesgos`): dos pestañas, Registro
 * y Matriz (con «Movimiento · N días» debajo), y el panel lateral de
 * detalle. Estado de pestaña en `?pestana=registro|matriz` (por defecto
 * matriz); `?riesgo=<id>` abre el panel; anclas `#registro`, `#matriz`,
 * `#movimiento`.
 */

import { useEffect } from "react";
import { useLocation, useSearchParams } from "react-router";

import { EmptyState, PageHeader, SinProyecto } from "@/components/vigia";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSession, useCan } from "@/session/session";
import { useTitulo } from "@/hooks/useTitulo";
import { Matriz } from "./Matriz";
import { Movimiento } from "./Movimiento";
import { PanelRiesgo } from "./PanelRiesgo";
import { Registro } from "./Registro";

type Pestana = "registro" | "matriz";

export default function RiesgosIndex() {
  useTitulo("Riesgos");
  const { projectId, role } = useSession();
  const puedeLeer = useCan("registros");
  const [params, setParams] = useSearchParams();
  const { hash } = useLocation();

  const pestana: Pestana = params.get("pestana") === "registro" ? "registro" : "matriz";
  const riesgoId = Number(params.get("riesgo")) || null;

  useEffect(() => {
    if (hash === "#registro" && pestana !== "registro") {
      const next = new URLSearchParams(params);
      next.set("pestana", "registro");
      setParams(next);
    } else if ((hash === "#matriz" || hash === "#movimiento") && pestana !== "matriz") {
      const next = new URLSearchParams(params);
      next.set("pestana", "matriz");
      setParams(next);
    }
    // Solo al montar: un clic posterior en las pestañas no debe pelearse con el hash de llegada.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps intencionalmente vacías, solo al montar.
  }, []);

  const cambiarPestana = (valor: string) => {
    const next = new URLSearchParams(params);
    next.set("pestana", valor);
    setParams(next);
  };

  const abrirRiesgo = (id: number) => {
    const next = new URLSearchParams(params);
    next.set("riesgo", String(id));
    setParams(next);
  };

  const cerrarPanel = () => {
    const next = new URLSearchParams(params);
    next.delete("riesgo");
    setParams(next);
  };

  if (projectId === null) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader titulo="Riesgos" />
        <SinProyecto que="sus riesgos" />
      </div>
    );
  }

  if (!puedeLeer) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader titulo="Riesgos" />
        <EmptyState
          titulo="Sin acceso"
          descripcion={`El rol «${role}» no ve la matriz de riesgos.`}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        titulo="Riesgos"
        descripcion="Registro y matriz de impacto x probabilidad de los riesgos abiertos en el proyecto."
      />
      <Tabs value={pestana} onValueChange={cambiarPestana}>
        <TabsList>
          <TabsTrigger value="matriz">Matriz</TabsTrigger>
          <TabsTrigger value="registro">Registro</TabsTrigger>
        </TabsList>
        <TabsContent value="matriz" className="flex flex-col gap-6">
          <Matriz projectId={projectId} onSelectRiesgo={abrirRiesgo} />
          <Movimiento projectId={projectId} />
        </TabsContent>
        <TabsContent value="registro">
          <Registro projectId={projectId} onSelectRiesgo={abrirRiesgo} />
        </TabsContent>
      </Tabs>

      <PanelRiesgo riesgoId={riesgoId} onClose={cerrarPanel} />
    </div>
  );
}
