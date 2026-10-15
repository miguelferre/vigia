/**
 * Sección «Datos» de `/ayuda` (`/ayuda#datos`): la guía de
 * datos de `GET /content/guia-datos` con las seis plantillas para descargar,
 * los formatos admitidos, cómo decidir la clase favorable y qué hacer si la
 * comprobación de codificación sale «inconclusa». El hash `#datos` (y
 * `#clase-favorable`, `#codificacion-inconclusa`) desplaza hasta aquí como
 * `#guia-N` (`ancla.ts`): la sección existe antes de que llegue el contenido.
 */

import { useEffect } from "react";
import { useLocation } from "react-router";

import { useGuiaDatos } from "@/api/queries-contenido";
import { ErrorDeConsulta } from "@/components/vigia";

import { programarScrollAId } from "./ancla";
import { DatosSeccion } from "./DatosSeccion";
import { DatosFormatos } from "./DatosFormatos";
import {
  ID_CLASE_FAVORABLE,
  ID_CODIFICACION,
  ID_DATOS,
  IDS_ANCLA_DATOS,
  INTRO_DATOS,
  RESPALDO_DATOS,
  TITULO_DATOS,
} from "./datos-textos";

export function Datos({ oculto }: { oculto: boolean }) {
  const guiaQ = useGuiaDatos();
  const { hash } = useLocation();
  const ancla = hash.replace(/^#/, "");
  useEffect(() => {
    if (IDS_ANCLA_DATOS.includes(ancla)) programarScrollAId(ancla);
  }, [ancla]);

  if (oculto) return null;
  const g = guiaQ.data;
  return (
    <section id={ID_DATOS} className="flex scroll-mt-28 flex-col gap-3">
      <h2 className="text-sm font-semibold">{TITULO_DATOS}</h2>
      <p className="text-sm text-muted-foreground">{INTRO_DATOS}</p>
      {guiaQ.isLoading ? (
        <p className="text-sm text-muted-foreground">Cargando la guía de datos…</p>
      ) : !g ? (
        guiaQ.isError ? (
          <ErrorDeConsulta
            que="la guía de datos"
            error={guiaQ.error}
            onReintentar={() => void guiaQ.refetch()}
          />
        ) : (
          <p className="text-sm text-muted-foreground">{RESPALDO_DATOS}</p>
        )
      ) : (
        <>
          <p className="text-sm text-tertiary">{g.resumen}</p>
          <p className="text-xs text-muted-foreground">{g.aviso_sintetico}</p>
          <div className="flex flex-col divide-y divide-border rounded-md border border-border px-4">
            {g.secciones.map((s) => (
              <DatosSeccion key={s.id} seccion={s} />
            ))}
          </div>
          <DatosFormatos
            formatos={g.formatos}
            claseFavorable={g.clase_favorable}
            inconclusa={g.codificacion_inconclusa}
            idClase={ID_CLASE_FAVORABLE}
            idInconclusa={ID_CODIFICACION}
          />
        </>
      )}
    </section>
  );
}
