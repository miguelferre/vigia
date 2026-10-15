/**
 * «Hecho al llegar»: un paso sin evento ni trabajo se da por hecho
 * cuando la ruta actual es la de su destino resuelto; los que sí los tienen,
 * solo si lo que piden ya existe (`yaSatisfecho`: reproducción adoptada con
 * `?run=` o vuelta atrás). Ajuste de estado en el render (patrón del repo),
 * con la ruta resuelta y `activa` en la clave para que cuente también cuando
 * la alerta o la activación llegan después de la navegación. Partido del
 * `Provider` para que ninguno de los dos pase de 9 KB.
 */

import { useState } from "react";

import type { PasoDemo } from "@/api/queries-contenido";

import type { DestinoResuelto } from "./destino";
import { esPasoConEvento, esPasoDeCarga, yaSatisfecho } from "./pasos";

export interface EstadoLlegada {
  activa: boolean;
  paso: number;
  projectId: number | null;
  runId: number | null;
  hechos: number[];
}

export function useHechoAlLlegar(
  pasos: PasoDemo[],
  estado: EstadoLlegada,
  destino: DestinoResuelto,
  pathname: string,
  fasesReproducidas: number,
  marcarHecho: (n: number) => void,
): void {
  const pasoActual = pasos[estado.paso] ?? null;
  const satisfecho = yaSatisfecho(pasos, estado.paso, {
    projectId: estado.projectId,
    runId: estado.runId,
    fasesReproducidas,
  });
  const clave = `${pathname}|${estado.paso}|${destino.pathname}|${estado.activa}|${satisfecho}`;
  const [claveVista, setClaveVista] = useState(clave);
  if (clave !== claveVista) {
    setClaveVista(clave);
    const porLlegada = pasoActual
      ? satisfecho || (!esPasoConEvento(pasoActual) && !esPasoDeCarga(pasos, estado.paso))
      : false;
    if (
      estado.activa &&
      destino.pathname !== null &&
      destino.pathname === pathname &&
      porLlegada &&
      !estado.hechos.includes(estado.paso)
    ) {
      marcarHecho(estado.paso);
    }
  }
}
