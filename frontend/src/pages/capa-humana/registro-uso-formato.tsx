/**
 * «Cómo preparar el registro de uso»: el formato del fichero con las
 * columnas, las fechas admitidas y el ejemplo descargable, desplegable bajo la
 * cabecera de `RegistroUso.tsx`. Todo sale de `GET /content/registro-uso`.
 */

import { Button } from "@/components/ui/button";
import { api, mensajeDeError } from "@/api/client";
import type { CapacidadesTarea } from "@/lib/tipo-tarea";
import { EnlaceFormato } from "@/pages/modelos/subida-enlace-formato";
import type { RegistroUsoAyuda } from "./registro-uso-ayuda";

interface Props {
  ayuda: RegistroUsoAyuda;
  onError: (texto: string) => void;
  /** Decisión del registro según el tipo de tarea. */
  decision: CapacidadesTarea["decisionHumana"];
  /** Clases del modelo multiclase; con ellas las tres columnas de decisión llevan nombres de clase. */
  clases?: string[];
}

const COLUMNAS_DE_CLASE = ["human_decision", "model_output", "ground_truth"];

export function FormatoRegistro({ ayuda, onError, decision, clases = [] }: Props) {
  const multiclase = decision === "clases";
  const regresion = decision === "rango";
  const valoresDeColumna = (nombre: string, original: string) => {
    if (!COLUMNAS_DE_CLASE.includes(nombre)) return original;
    const vacio = nombre === "ground_truth" ? "En blanco si todavía no se sabe." : "En blanco se guarda como sin dato.";
    if (multiclase) return `Una de las clases del modelo: ${clases.join(", ")}. No se admite refer ni no-refer. ${vacio}`;
    if (regresion) return `Un número en la unidad del modelo, con punto decimal y sin la unidad. No se admite refer ni no-refer. ${vacio}`;
    return original;
  };
  // En multiclase se descarga el ejemplo con nombres de clase (`?tipo=multiclass`).
  const ejemploMulticlase = multiclase ? (ayuda.ejemplo_multiclase ?? null) : null;
  // En regresión se descarga el ejemplo con cifras (`?tipo=regression`).
  const ejemploRegresion = regresion ? (ayuda.ejemplo_regresion ?? null) : null;
  const ejemploCifras = ejemploMulticlase ?? ejemploRegresion;
  const descargarEjemplo = async () => {
    try {
      if (ejemploRegresion) {
        await api.download("/content/registro-uso/ejemplo.csv", ejemploRegresion.nombre_fichero, {
          params: { tipo: "regression" },
        });
      } else if (ejemploMulticlase) {
        await api.download("/content/registro-uso/ejemplo.csv", ejemploMulticlase.nombre_fichero, {
          params: { tipo: "multiclass" },
        });
      } else {
        await api.download("/content/registro-uso/ejemplo.csv", ayuda.ejemplo.nombre_fichero);
      }
    } catch (err) {
      onError(mensajeDeError(err));
    }
  };
  return (
    <div className="flex flex-col gap-2">
      <details className="rounded-md border border-border p-3 text-sm" data-testid="registro-uso-formato">
        <summary className="cursor-pointer font-medium">{ayuda.titulo}</summary>
        <div className="mt-2 flex flex-col gap-2">
          <p className="text-xs text-muted-foreground">{ayuda.formato_fichero}</p>
          <ul className="flex flex-col gap-1 text-xs">
            {ayuda.columnas_obligatorias.map((c) => (
              <li key={c.nombre}>
                <code className="rounded bg-muted px-1">{c.nombre}</code> {c.que_es} {valoresDeColumna(c.nombre, c.valores)}
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">
            Fechas admitidas: {ayuda.formatos_fecha.map((f) => `${f.formato} (${f.ejemplo})`).join(", ")}.
          </p>
          {(multiclase && !ejemploMulticlase) || (regresion && !ejemploRegresion) ? (
            <p className="text-xs text-muted-foreground">
              El ejemplo descargable usa refer y no-refer: vale solo para modelos binarios. Para este modelo, escribe
              {multiclase ? " el nombre de la clase" : " la cifra"} en cada decisión.
            </p>
          ) : (
            <div className="flex flex-col gap-1.5">
              <div className="flex flex-wrap items-center gap-3">
                <Button size="sm" variant="outline" onClick={() => void descargarEjemplo()}>
                  {ejemploMulticlase ? "Descargar ejemplo multiclase" : ejemploRegresion ? "Descargar ejemplo de regresión" : "Descargar ejemplo"}
                </Button>
              </div>
              {ejemploCifras ? (
                <p className="text-xs text-muted-foreground" data-testid={multiclase ? "registro-uso-ejemplo-multiclase-nota" : "registro-uso-ejemplo-regresion-nota"}>
                  {ejemploCifras.nota}
                </p>
              ) : null}
            </div>
          )}
        </div>
      </details>
      {/* Fuera del desplegable: el enlace se ve con la ayuda cerrada. */}
      <EnlaceFormato className="w-fit" />
    </div>
  );
}
