/**
 * Bloque «Empezar» del estado vacío de `/`: tres caminos y,
 * encima, el enlace a la guía de datos. «Crear modelo» queda solo en la
 * cabecera de la pantalla; aquí el primario se llama «Dar de alta tu modelo».
 */

import { Link } from "react-router";
import { BookOpenIcon, BotIcon, PlayIcon, PlusIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/vigia";

import {
  AYUDA_CAMINOS,
  CAMINOS,
  DESCRIPCION_EMPEZAR,
  ENLACE_DATOS,
  RUTA_ASISTENTE,
  RUTA_DEMO,
  TITULO_EMPEZAR,
} from "./portada-empezar-textos";

export function PortadaEmpezar({ onAlta }: { onAlta: () => void }) {
  return (
    <div className="flex flex-col gap-3">
      <Link
        to={ENLACE_DATOS.ruta}
        className="inline-flex w-fit items-center gap-1.5 text-sm text-primary underline underline-offset-2"
      >
        <BookOpenIcon className="size-4" aria-hidden="true" />
        {ENLACE_DATOS.texto}
      </Link>
      <EmptyState
        titulo="Todavía no hay modelos"
        descripcion={
          <>
            <span className="block font-medium text-foreground">{TITULO_EMPEZAR}</span>
            {DESCRIPCION_EMPEZAR}
          </>
        }
        accion={
          <div className="flex w-full max-w-xl flex-col gap-3">
            <div className="flex flex-wrap justify-center gap-2">
              <Button onClick={onAlta}>
                <PlusIcon className="size-4" aria-hidden="true" />
                {CAMINOS.alta}
              </Button>
              <Button asChild variant="outline">
                <Link to={RUTA_DEMO}>
                  <PlayIcon className="size-4" aria-hidden="true" />
                  {CAMINOS.demo}
                </Link>
              </Button>
            </div>
            <Link
              to={RUTA_ASISTENTE}
              className="inline-flex items-center justify-center gap-1.5 text-sm text-primary underline underline-offset-2"
            >
              <BotIcon className="size-4" aria-hidden="true" />
              {CAMINOS.asistente}
            </Link>
            <ul className="flex flex-col gap-0.5 text-xs text-muted-foreground">
              <li>{AYUDA_CAMINOS.alta}</li>
              <li>{AYUDA_CAMINOS.demo}</li>
              <li>{AYUDA_CAMINOS.asistente}</li>
            </ul>
          </div>
        }
      />
    </div>
  );
}
