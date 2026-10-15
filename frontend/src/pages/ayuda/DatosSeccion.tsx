/**
 * Un fichero de la guía de datos (`GuiaDatosSeccion`): para qué sirve, sus
 * columnas y la descarga de su plantilla CSV (`/api/content/plantillas/{tipo}.csv`).
 * Las columnas van como lista y no como tabla para que a 375 px no desborde.
 */

import { DownloadIcon } from "lucide-react";

import { API_BASE } from "@/api/client";
import type { GuiaDatosColumna, GuiaDatosSeccion } from "@/api/queries-contenido";
import { Button } from "@/components/ui/button";

import {
  COLUMNAS_OBLIGATORIAS,
  COLUMNAS_OPCIONALES,
  DESCARGAR,
  SIN_PLANTILLA,
} from "./datos-textos";

function Columnas({ titulo, columnas }: { titulo: string; columnas: GuiaDatosColumna[] }) {
  if (columnas.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <h4 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{titulo}</h4>
      <ul className="flex flex-col gap-2 text-sm">
        {columnas.map((c) => (
          <li key={c.nombre} className="flex flex-col gap-0.5">
            <span>
              <code className="font-mono text-xs font-semibold">{c.nombre}</code>{" "}
              <span className="text-muted-foreground">{c.que_es}</span>
            </span>
            <span className="text-xs text-muted-foreground">
              {c.valores} Ejemplo: <code className="font-mono">{c.ejemplo}</code>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DatosSeccion({ seccion: s }: { seccion: GuiaDatosSeccion }) {
  return (
    <div id={`datos-${s.id}`} className="flex scroll-mt-20 flex-col gap-3 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{s.titulo}</h3>
        {s.plantilla ? (
          <Button asChild variant="outline" size="sm">
            <a href={`${API_BASE}/content/plantillas/${s.plantilla}.csv`} download={s.nombre_plantilla ?? undefined}>
              <DownloadIcon className="size-4" aria-hidden="true" />
              {DESCARGAR}
              <span className="sr-only">: {s.titulo}</span>
            </a>
          </Button>
        ) : (
          <span className="text-xs text-muted-foreground">{SIN_PLANTILLA}</span>
        )}
      </div>
      <p className="text-sm text-tertiary">{s.para_que}</p>
      {s.tipo_en_vigia ? <p className="text-xs text-muted-foreground">Al subirlo, tipo: {s.tipo_en_vigia}.</p> : null}
      <Columnas titulo={COLUMNAS_OBLIGATORIAS} columnas={s.obligatorias} />
      <Columnas titulo={COLUMNAS_OPCIONALES} columnas={s.opcionales} />
      {s.notas.length > 0 ? (
        <ul className="list-disc pl-5 text-xs text-muted-foreground">
          {s.notas.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
