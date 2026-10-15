/**
 * Bloque B del drill-down de equidad: tasas de error por
 * grupo (`fnr`, `fpr`, `tpr`), en tabla comparativa. Estas ocho medidas no
 * tienen umbral configurado, así que la rejilla de monitores no las
 * enseña; hoy solo salían como fila suelta en inglés en el sheet de detalle.
 *
 * Denominador: `details.counts_label` (ventana con etiqueta), distinto del
 * `details.counts` que usa el bloque A. Ver cabecera de `DrillImpactoDispar.tsx`.
 *
 * Partido de ese fichero porque las dos piezas juntas pasaban de 9 KB.
 */

import { cn } from "@/lib/utils";
import { useGuionDemo } from "@/api/queries-contenido";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { textoRangos } from "@/lib/metrics";
import type { EvaluationDetail } from "@/api/types";

import { formatoPorcentaje, medida, numero } from "./calculo-datos";
import { EtiquetaConAyuda } from "./EtiquetaConAyuda";
import { nombreReferencia, nombreSupervisado, useGroupContext } from "./contexto-grupos";

/**
 * La etiqueta de la fila no nombra al grupo: cada columna ya es un grupo, y
 * repetirlo ("Tasa de falsos negativos, grupo supervisado" en la fila de la
 * columna "grupo de referencia") se lee mal. El nombre completo queda en el ⓘ.
 */
const METRICAS_ERROR: { clave: string; etiquetaCorta: string }[] = [
  { clave: "tpr", etiquetaCorta: "Sensibilidad (tpr)" },
  { clave: "fnr", etiquetaCorta: "Tasa de falsos negativos (fnr)" },
  { clave: "fpr", etiquetaCorta: "Tasa de falsos positivos (fpr)" },
];

/** Barra proporcional a la tasa (0-100 %) dentro de la celda, con el número como texto encima. */
function CeldaTasa({ valor, resaltada }: { valor: number | null; resaltada: boolean }) {
  const pct = valor !== null && !Number.isNaN(valor) ? Math.min(100, Math.max(0, valor * 100)) : null;
  return (
    <div className="relative">
      {pct !== null ? (
        <div
          className={cn("absolute inset-y-0 left-0 rounded-sm", resaltada ? "bg-foreground/15" : "bg-foreground/10")}
          style={{ width: `${pct}%` }}
          aria-hidden="true"
        />
      ) : null}
      <span className="relative tabular-nums">{formatoPorcentaje(valor)}</span>
    </div>
  );
}

export interface DrillTasasErrorProps {
  evaluacion: EvaluationDetail;
  /** Filas (`fnr`/`fpr`/`tpr`) implicadas en la fórmula de la métrica ampliada. */
  resaltar?: string[];
}

export function DrillTasasError({ evaluacion, resaltar }: DrillTasasErrorProps) {
  const detalles = (evaluacion.result?.details ?? null) as Record<string, unknown> | null;
  const countsLabel = (detalles?.counts_label ?? null) as Record<string, unknown> | null;
  const nUnpriv = numero(countsLabel?.n_unpriv);
  const nPriv = numero(countsLabel?.n_priv);
  const ctx = useGroupContext();
  const dominio = useGuionDemo().data?.dominio;
  const { caps, rangos, unidad } = useTipoTarea(evaluacion.project_id);
  const etiquetaSupervisado = nombreSupervisado(ctx, dominio);
  const etiquetaReferencia = nombreReferencia(ctx, dominio);

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        Sobre la ventana con etiqueta
        {nUnpriv !== null && nPriv !== null ? (
          <>
            {" "}
            ({etiquetaSupervisado} n = {nUnpriv}, {etiquetaReferencia} n = {nPriv})
          </>
        ) : null}
        , que es distinta de la ventana de predicciones con la que se calcula la tasa favorable.
        Estas tasas por grupo no tienen umbral propio: son el desglose de las diferencias de arriba.
        {caps?.favorables === "conjunto"
          ? " Con varias clases, «positivo» quiere decir que la clase cae en una de las favorables y «negativo», que es cualquier otra."
          : caps?.rangoFavorable
            ? ` Con un rango favorable (${textoRangos(rangos, unidad)}), «positivo» quiere decir que el valor cae dentro del rango y «negativo», que cae fuera.`
            : ""}
      </p>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full caption-bottom text-sm">
          <thead className="[&_tr]:border-b">
            <tr className="border-b">
              <th className="h-9 px-3 text-left align-middle text-muted-foreground">Medida</th>
              <th className="h-9 px-3 text-left align-middle text-muted-foreground">{etiquetaSupervisado}</th>
              <th className="h-9 px-3 text-left align-middle text-muted-foreground">{etiquetaReferencia}</th>
            </tr>
          </thead>
          <tbody>
            {METRICAS_ERROR.map(({ clave, etiquetaCorta }) => {
              const mU = medida(evaluacion, `${clave}_unpriv`);
              const mP = medida(evaluacion, `${clave}_priv`);
              const resaltada = resaltar?.includes(clave) ?? false;
              return (
                <tr key={clave} className="border-b last:border-0">
                  <td className="p-3 align-middle">
                    <EtiquetaConAyuda
                      clave={`${clave}_unpriv`}
                      etiquetaAlt={etiquetaCorta}
                      etiquetaVisible={etiquetaCorta}
                    />
                  </td>
                  <td className={cn("p-3 align-middle tabular-nums", resaltada && "bg-muted font-semibold")}>
                    <CeldaTasa valor={mU?.value ?? null} resaltada={resaltada} />
                  </td>
                  <td className={cn("p-3 align-middle tabular-nums", resaltada && "bg-muted font-semibold")}>
                    <CeldaTasa valor={mP?.value ?? null} resaltada={resaltada} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default DrillTasasError;
