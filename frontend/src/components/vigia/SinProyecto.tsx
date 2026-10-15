/**
 * Estado vacío común de las pantallas que exigen un modelo: Alertas, Explicabilidad, Capa humana, Auditoría, Riesgos, Cuadro,
 * Monitores y Diario. Sin modelos, lleva al alta; con modelos y ninguno
 * elegido, manda al selector de la cabecera y a Modelos. Nunca sin botón.
 */

import { Link } from "react-router";
import { PlusIcon } from "lucide-react";

import { useProjects } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { EmptyState } from "./EmptyState";
import { ErrorDeConsulta } from "./ErrorDeConsulta";
import {
  RUTA_ALTA_MODELO,
  TEXTO_ALTA,
  TEXTO_IR_A_MODELOS,
  TITULO_ELIGE_MODELO,
  TITULO_SIN_MODELOS,
  descripcionEligeModelo,
  descripcionSinModelos,
} from "./sin-proyecto-textos";

export interface SinProyectoProps {
  /** Lo que la pantalla enseña de un modelo, para la frase: «sus alertas». */
  que: string;
}

export function SinProyecto({ que }: SinProyectoProps) {
  const { data, isPending, isError, error, refetch } = useProjects({ limit: 200 });
  if (isPending) return <Skeleton className="h-40 w-full" data-loading="true" />;
  // Con el programa cerrado no se invita a dar de alta un modelo: se dice que
  // no hay conexión y se deja reintentar.
  if (isError) {
    return <ErrorDeConsulta que="los modelos" error={error} onReintentar={() => void refetch()} />;
  }
  const hayModelos = (data?.items.length ?? 0) > 0;
  if (!hayModelos) {
    return (
      <EmptyState
        titulo={TITULO_SIN_MODELOS}
        descripcion={descripcionSinModelos(que)}
        accion={
          <Button asChild>
            <Link to={RUTA_ALTA_MODELO}>
              <PlusIcon className="size-4" aria-hidden="true" />
              {TEXTO_ALTA}
            </Link>
          </Button>
        }
      />
    );
  }
  return (
    <EmptyState
      titulo={TITULO_ELIGE_MODELO}
      descripcion={descripcionEligeModelo(que)}
      accion={
        <Button asChild variant="outline">
          <Link to="/modelos">{TEXTO_IR_A_MODELOS}</Link>
        </Button>
      }
    />
  );
}
