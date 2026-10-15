/**
 * Drill-down del impacto dispar: cómo se
 * calcula el DI paso a paso. La tabla de tasas de error por grupo vive en
 * `drill-tasas-error.tsx` (mismo fichero se acercaba a 9 KB con las dos
 * piezas). `pages/monitores/calculo.tsx` elige el drill-down por
 * `monitor_type` y le pasa la evaluación completa.
 *
 * Denominador de este bloque: `details.counts` (ventana de predicción), no
 * `details.counts_label` (ventana con etiqueta, que usa el otro bloque). Es
 * el error fácil de esta pantalla, verificado en vivo sobre la evaluación 1
 * de la demo (`n_unpriv` 34, `n_priv` 132 en `counts`; 67 y 310 en
 * `counts_label`).
 *
 * Vocabulario: nunca "unpriv"/"priv" en texto visible,
 * siempre "grupo supervisado" y "grupo de referencia". Ninguna medida de
 * esta evaluación trae `group_label` (siempre `null` en los datos de demo);
 * el día que el backend lo mande, antepone al término genérico.
 *
 * Con `group_context` ("chip en
 * la cabecera «Supervisado: sexo = mujer · Referencia: sexo = hombre»") ya
 * no basta el término genérico: `GroupContextProvider` (`contexto-grupos.tsx`)
 * reparte el contexto de grupos por React Context (`monitores/index.tsx` lo
 * monta con `monitor.group_context`) para no tocar `CalculoMetrica.tsx`,
 * fuera de esta frontera, que renderiza este drill sin pasarle nada nuevo.
 * `nombreSupervisado`/`nombreReferencia` degradan al término genérico si no
 * hay contexto (alerta, laboratorio) o si `group_context` es `null`.
 *
 * `medida`, `numero` y los formateadores viven en `calculo-datos.ts`, y
 * `EtiquetaConAyuda` en su propio fichero. Ninguno se reexporta
 * desde aquí: la reexportación cerraba otra vez el ciclo, esta vez pasando
 * por `ViolinPartido.tsx`. Impórtalos del módulo hoja.
 */

import { useGuionDemo } from "@/api/queries-contenido";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { textoRangos } from "@/lib/metrics";
import { Separator } from "@/components/ui/separator";
import type { EvaluationDetail } from "@/api/types";
import { nombreReferencia, nombreSupervisado, useGroupContext } from "./contexto-grupos";

import { formatoPorcentaje, medida, numero } from "./calculo-datos";
import { EtiquetaConAyuda } from "./EtiquetaConAyuda";
import { ColumnasCalculo, EscalaCociente } from "./CalculoFormula";
import { DrillTasasError } from "./DrillTasasError";


interface FilaGrupo {
  etiqueta: string;
  clave: string;
  positivos: number | null;
  n: number | null;
  tasa: number | null;
  derivado: boolean;
}

function filaDeGrupo(
  etiqueta: string,
  clave: string,
  tasa: number | null,
  n: number | null,
  positivosDirectos: number | null,
): FilaGrupo {
  let positivos = positivosDirectos;
  let derivado = false;
  if (positivos === null && tasa !== null && n !== null) {
    positivos = Math.round(tasa * n);
    derivado = true;
  }
  return { etiqueta, clave, positivos, n, tasa, derivado };
}

/** Barra horizontal de la tasa favorable de un grupo (0-100 %), con el número real como pie. */
function BarraTasaFavorable({ fila }: { fila: FilaGrupo }) {
  const pct = fila.tasa !== null && !Number.isNaN(fila.tasa) ? Math.min(100, Math.max(0, fila.tasa * 100)) : null;
  return (
    <div className="rounded-lg border p-3">
      <div className="mb-1.5 flex items-baseline justify-between gap-2 text-xs text-muted-foreground">
        <EtiquetaConAyuda clave={fila.clave} etiquetaAlt={`Tasa favorable, ${fila.etiqueta}`} />
        <span className="shrink-0 font-semibold tabular-nums text-foreground">{formatoPorcentaje(fila.tasa)}</span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-muted" role="img" aria-label={`${fila.etiqueta}: ${formatoPorcentaje(fila.tasa)}`}>
        {pct !== null ? <div className="h-full rounded-full" style={{ width: `${pct}%`, background: "var(--chart-2)" }} /> : null}
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">
        {fila.positivos !== null && fila.n !== null ? (
          <>
            {fila.positivos} de {fila.n}
            {fila.derivado ? " (estimado)" : ""}
          </>
        ) : (
          "n/d"
        )}
      </p>
    </div>
  );
}

function BloqueCalculo({ evaluacion }: { evaluacion: EvaluationDetail }) {
  const detalles = (evaluacion.result?.details ?? null) as Record<string, unknown> | null;
  const counts = (detalles?.counts ?? null) as Record<string, unknown> | null;
  const ctx = useGroupContext();
  const dominio = useGuionDemo().data?.dominio;
  // en multiclase, el texto dice qué clases cuentan como favorables; la cuenta es la misma.
  // en regresión con rango, «favorable» es estar dentro del rango.
  const { caps, favorables: favorablesProyecto, rangos, unidad } = useTipoTarea(evaluacion.project_id);
  const favorables = caps?.favorables === "conjunto" ? favorablesProyecto : [];
  const textoRango = caps?.rangoFavorable ? textoRangos(rangos, unidad) : "";

  const mUnpriv = medida(evaluacion, "rate_unpriv");
  const mPriv = medida(evaluacion, "rate_priv");
  const mDi = medida(evaluacion, "fairness_value");

  const filas: FilaGrupo[] = [
    filaDeGrupo(nombreSupervisado(ctx, dominio), "rate_unpriv", mUnpriv?.value ?? null, numero(counts?.n_unpriv), numero(counts?.positives_unpriv)),
    filaDeGrupo(nombreReferencia(ctx, dominio), "rate_priv", mPriv?.value ?? null, numero(counts?.n_priv), numero(counts?.positives_priv)),
  ];

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        {favorables.length > 0
          ? `Tasa con que cada grupo recibe una de las clases favorables (${favorables.join(", ")}), sobre la ventana de predicción.`
          : textoRango
            ? `Tasa con que cada grupo recibe un valor dentro del rango favorable (${textoRango}), sobre la ventana de predicción.`
            : "Tasa de resultado favorable de cada grupo, sobre la ventana de predicción."}
      </p>
      {/* la fórmula pasa a ser la pieza principal, a la derecha de la
          tabla de numerador y denominador (dos columnas desde `@lg`). */}
      <ColumnasCalculo
        tabla={
          <div className="grid gap-3 sm:grid-cols-2">
            {filas.map((fila) => (
              <BarraTasaFavorable key={fila.clave} fila={fila} />
            ))}
          </div>
        }
        formula={
          <EscalaCociente
            mDi={mDi}
            mUnpriv={mUnpriv}
            mPriv={mPriv}
            detalles={detalles}
            nombreSupervisado={nombreSupervisado(ctx, dominio)}
            nombreReferencia={nombreReferencia(ctx, dominio)}
          />
        }
      />

      {filas.some((f) => f.derivado) ? (
        <p className="text-xs text-muted-foreground">
          El numerador de al menos un grupo es una estimación (tasa x tamaño de ventana,
          redondeado): Vigía no recibe los positivos por grupo de este caso.
        </p>
      ) : null}
    </div>
  );
}

export interface DrillImpactoDisparProps {
  evaluacion: EvaluationDetail;
}

export function DrillImpactoDispar({ evaluacion }: DrillImpactoDisparProps) {
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold">Cómo se calcula el impacto dispar</h3>
        <BloqueCalculo evaluacion={evaluacion} />
      </section>
      <Separator />
      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold">Tasas de error por grupo</h3>
        <DrillTasasError evaluacion={evaluacion} />
      </section>
    </div>
  );
}

export default DrillImpactoDispar;
