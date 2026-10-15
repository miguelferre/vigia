/**
 * Capa humana (ruta `/capa-humana`): seis bloques con ancla propia (registro de uso, deskilling, overrides,
 * vista propia, cruzadas, outcomes). Rol `cliente`: `EmptyState` sin
 * llamar a la API (ninguna capacidad nueva).
 */

import { useState } from "react";
import { useLocation } from "react-router";

import { EmptyState, PageHeader, SinProyecto } from "@/components/vigia";
import { useCan, useSession } from "@/session/session";
import { useTitulo } from "@/hooks/useTitulo";
import { RegistroUso } from "./RegistroUso";
import { Deskilling } from "./Deskilling";
import { Overrides } from "./Overrides";
import { VistaPropia } from "./VistaPropia";
import { Cruzadas } from "./Cruzadas";
import { Outcomes } from "./Outcomes";

const ANCLAS = ["registro-uso", "deskilling", "overrides", "vista-propia", "cruzadas", "outcomes"] as const;

function useDesplazarHash() {
  const { hash } = useLocation();
  const [aplicado, setAplicado] = useState<string | null>(null);
  if (hash && hash !== aplicado) {
    setAplicado(hash);
    const id = hash.slice(1);
    if ((ANCLAS as readonly string[]).includes(id)) {
      // Los cinco bloques piden datos por su cuenta y crecen según llegan
      // (tabla, gráfica, resumen): un único desplazamiento en el primer
      // tick puede quedar corto si el bloque de destino aún no tiene su
      // contenido. Se repite mientras la página se asienta, en vez de un
      // solo intento (variante del patrón de `pages/monitores/index.tsx`).
      for (const espera of [0, 200, 500, 900, 1400]) {
        window.setTimeout(() => {
          document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, espera);
      }
    }
  }
}

export default function CapaHumanaIndex() {
  useTitulo("Capa humana");
  const { projectId } = useSession();
  const puedeLeer = useCan("registros");
  useDesplazarHash();

  if (!puedeLeer) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader titulo="Capa humana" />
        <EmptyState
          titulo="Esta pantalla no está disponible para tu rol"
          descripcion="La capa humana (deskilling, overrides, cruzadas y outcomes) se enseña a gestor, auditor y profesional."
        />
      </div>
    );
  }

  if (projectId === null) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader titulo="Capa humana" />
        <SinProyecto que="su capa humana" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        titulo="Capa humana"
        descripcion="Cómo usan el modelo los profesionales y qué pasa con las personas afectadas: apoyo, overrides, alertas cruzadas y resultados agregados."
      />
      <RegistroUso projectId={projectId} />
      <Deskilling projectId={projectId} />
      <Overrides projectId={projectId} />
      <VistaPropia projectId={projectId} />
      <Cruzadas projectId={projectId} />
      <Outcomes projectId={projectId} />
    </div>
  );
}
