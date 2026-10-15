/**
 * Pasos con estado de una versión nueva sin activar: subir
 * su línea base, congelarla, subir el modelo (opcional) y activarla. Ingerir
 * una línea base ya congela la versión, así que el paso 2 sale hecho
 * en cuanto sale el 1. El estado se lee de la propia versión: `baseline_batch_id`,
 * `frozen_at` y `artifact_sha256`.
 */

import { CheckCircle2Icon, CircleIcon } from "lucide-react";

import type { ModelVersion } from "@/api/types";
import { Button } from "@/components/ui/button";
import { estadoPasos } from "./versiones-pasos-estado";
import { PASOS_VERSION, TITULO_PASOS, type PasoVersion } from "./versiones-textos";

export interface AccionesPasos {
  onIrADatos: () => void;
  onFijarLineaBase: (v: ModelVersion) => void;
  onSubirArtefacto: (v: ModelVersion) => void;
  onActivar: (v: ModelVersion) => void;
}

type EstadoPaso = "hecho" | "pendiente" | "opcional";

function textoEstado(hecho: boolean, opcional?: boolean): { texto: string; estado: EstadoPaso } {
  if (hecho) return { texto: "Hecho", estado: "hecho" };
  return opcional ? { texto: "Opcional, sin hacer", estado: "opcional" } : { texto: "Pendiente", estado: "pendiente" };
}

export function PasosVersion({ version, acciones }: { version: ModelVersion; acciones: AccionesPasos }) {
  const hechos = estadoPasos(version);
  const boton = (clave: PasoVersion["clave"]) => {
    if (hechos[clave]) return null;
    if (clave === "linea-base")
      return (
        <Button size="sm" variant="outline" onClick={acciones.onIrADatos}>
          Ir a Datos
        </Button>
      );
    if (clave === "congelar")
      return (
        <Button size="sm" variant="outline" onClick={() => acciones.onFijarLineaBase(version)}>
          Fijar línea base
        </Button>
      );
    if (clave === "modelo")
      return (
        <Button size="sm" variant="outline" onClick={() => acciones.onSubirArtefacto(version)}>
          Subir modelo
        </Button>
      );
    return (
      <Button size="sm" onClick={() => acciones.onActivar(version)}>
        Activar
      </Button>
    );
  };

  return (
    <section
      className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4"
      data-pasos-version={version.id ?? ""}
    >
      <h3 className="text-sm font-semibold">
        {TITULO_PASOS} «{version.label}»
      </h3>
      <ol className="flex flex-col divide-y divide-border">
        {PASOS_VERSION.map((p) => {
          const { texto, estado } = textoEstado(hechos[p.clave], p.opcional);
          const Icono = estado === "hecho" ? CheckCircle2Icon : CircleIcon;
          return (
            <li
              key={p.clave}
              data-paso={p.clave}
              data-estado={estado}
              className="flex flex-wrap items-start justify-between gap-2 py-2"
            >
              <div className="flex min-w-0 flex-1 items-start gap-2">
                <Icono
                  className="mt-0.5 size-4 shrink-0"
                  style={{ color: estado === "hecho" ? "var(--state-ok)" : "var(--muted-foreground)" }}
                  aria-hidden="true"
                />
                <div className="flex min-w-0 flex-col">
                  <span className="text-sm font-medium">
                    {p.titulo} <span className="font-normal text-muted-foreground">· {texto}</span>
                  </span>
                  <span className="text-xs text-muted-foreground">{p.ayuda}</span>
                </div>
              </div>
              {boton(p.clave)}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
