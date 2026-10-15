/**
 * Instanciación genérica de la fórmula de una métrica:
 * cada variable de `formula_vars` se resuelve como `metric_key` hermano o
 * como ruta `details.a.b`, se formatea y se compara con el
 * umbral. Si no se resuelve, no se inventa.
 *
 * La presentación (fórmula, instanciada, resultado, umbral, estado)
 * vive en `CajaFormula.tsx`, forma única de todo cálculo con `formula`.
 * Resultado y estado dependen del valor propio de la medida, no de que
 * `formula_vars` resuelva: métricas sin variables (`confidence_drift_score`,
 * `explain_stability_ndcg`) los enseñan también.
 */

import type { ReactNode } from "react";

import { type AyudaMetrica, type ContenidoMetricas } from "@/api/queries-contenido";
import type { EvaluationDetail } from "@/api/types";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { esMedidaEnUnidad, formatoMetrica, formatoNumero, metricLabel, metricLabelPorTipo } from "@/lib/metrics";
import { ayudaPorTipo } from "@/lib/tipo-tarea";

import { CajaFormula } from "./CajaFormula";
import { medida, numero } from "./calculo-datos";
import { motivoMulticlase, textoUmbralRelativo } from "./calculo-motivos";

export { EscalaCociente, type EscalaCocienteProps } from "./EscalaCociente";

const ETIQUETA_CONFUSION: Record<string, string> = { tp: "VP", tn: "VN", fp: "FP", fn: "FN" };

/**
 * Etiqueta de una variable de `formula_vars`: la `etiqueta` de
 * `metricas-ayuda.json` antes que `metricLabel`, que solo cubre las métricas
 * con umbral propio (`rate_unpriv`/`rate_priv` saldrían en crudo si no).
 */
function etiquetaVariable(nombre: string, todaAyuda: ContenidoMetricas | undefined): string {
  if (nombre.startsWith("details.")) {
    const clave = nombre.split(".").pop() ?? nombre;
    return ETIQUETA_CONFUSION[clave] ?? clave.replace(/_/g, " ");
  }
  return todaAyuda?.[nombre]?.etiqueta ?? metricLabel(nombre);
}

function resolverVariable(nombre: string, evaluacion: EvaluationDetail): number | null {
  if (nombre.startsWith("details.")) {
    const partes = nombre.split(".").slice(1);
    let actual: unknown = evaluacion.result?.details ?? null;
    for (const parte of partes) {
      if (actual === null || typeof actual !== "object" || Array.isArray(actual)) return null;
      actual = (actual as Record<string, unknown>)[parte];
    }
    return numero(actual);
  }
  return numero(medida(evaluacion, nombre)?.value);
}

/** Dígitos decimales del umbral (espejo de `core/states.py:_decimales_de`): entre 2 y 3. */
export function decimalesDe(umbral: number | null): number {
  if (umbral === null) return 3;
  const texto = Math.abs(umbral).toString();
  const punto = texto.indexOf(".");
  const decimales = punto === -1 ? 0 : texto.length - punto - 1;
  return Math.min(3, Math.max(2, decimales));
}

export interface UmbralResuelto {
  low: number | null;
  high: number | null;
}

/** El umbral de la propia medida si lo trae; si no, `umbral_por_defecto` del contenido. */
export function umbralResuelto(
  ayuda: AyudaMetrica,
  m: { threshold_low: number | null; threshold_high: number | null } | undefined,
): UmbralResuelto {
  if (m && (m.threshold_low !== null || m.threshold_high !== null)) {
    return { low: m.threshold_low, high: m.threshold_high };
  }
  return {
    low: ayuda.umbral_por_defecto?.limite_inferior ?? null,
    high: ayuda.umbral_por_defecto?.limite_superior ?? null,
  };
}

/**
 * «Umbral: mínimo X» / «máximo Y» (los dos si hay ambos); `null` sin umbral configurado.
 * `formato`: en regresión, el límite con la unidad del proyecto.
 */
function umbralTexto(umbral: UmbralResuelto, formato?: (v: number) => string): string | null {
  const decimales = decimalesDe(umbral.low ?? umbral.high);
  const f = formato ?? ((v: number) => formatoNumero(v, decimales));
  const partes: string[] = [];
  if (umbral.low !== null) partes.push(`mínimo ${f(umbral.low)}`);
  if (umbral.high !== null) partes.push(`máximo ${f(umbral.high)}`);
  return partes.length > 0 ? `Umbral: ${partes.join(" · ")}` : null;
}

export interface FormulaInstanciadaProps {
  metricKey: string;
  ayuda: AyudaMetrica;
  evaluacion: EvaluationDetail;
  /** El diccionario completo, para poner nombre a las variables que son medidas hermanas. */
  todaAyuda: ContenidoMetricas | undefined;
}

/**
 * `CajaFormula` con las variables resueltas: basta `ayuda.formula`
 * (ninguna métrica trae `formula_vars` sin ella). Resultado y estado salen
 * del valor propio, no de que las variables resuelvan: sin ellas
 * (`confidence_drift_score`, `explain_stability_ndcg`) se enseñan igual; si
 * no resuelven, la instanciada avisa y el resultado se mantiene.
 */
export function FormulaInstanciada({ metricKey, ayuda, evaluacion, todaAyuda }: FormulaInstanciadaProps) {
  const { caps, tipo, unidad } = useTipoTarea(evaluacion.project_id);
  const regresion = caps?.metricas === "regresion";
  // en regresión el resultado, el umbral y las variables en la unidad salen con ella.
  const formatoEnUnidad = (v: number) => formatoMetrica(metricKey, v, unidad);
  // la ayuda ya llega resuelta por tipo desde `useContenidoMetricasPorTipo`; aquí se
  // vuelve a aplicar por si quien llama pasó la entrada cruda (idempotente: sin bloque, la misma).
  ayuda = ayudaPorTipo(ayuda, tipo);
  if (!ayuda.formula) return null;

  const vars = ayuda.formula_vars && ayuda.formula_vars.length > 0 ? ayuda.formula_vars : null;
  const propia = medida(evaluacion, metricKey);
  const tieneValor = propia !== undefined && propia.value !== null && propia.value !== undefined;
  const resueltas = vars?.map((v) => ({ nombre: v, valor: resolverVariable(v, evaluacion) })) ?? null;
  const todasResueltas = resueltas !== null && resueltas.every((r) => r.valor !== null);
  const umbral = tieneValor && propia ? umbralResuelto(ayuda, propia) : null;
  const decimales = decimalesDe(umbral ? (umbral.low ?? umbral.high) : null);

  const instanciada: ReactNode =
    resueltas === null
      ? undefined
      : todasResueltas
        ? resueltas.map((r, i) => (
            <span key={r.nombre}>
              {i > 0 ? " · " : ""}
              {etiquetaVariable(r.nombre, todaAyuda)} ={" "}
              {regresion && esMedidaEnUnidad(r.nombre)
                ? formatoMetrica(r.nombre, r.valor, unidad)
                : formatoNumero(r.valor, Number.isInteger(r.valor) ? 0 : 3)}
            </span>
          ))
        : "Los valores por grupo no están disponibles en esta evaluación.";

  return (
    <CajaFormula
      formula={ayuda.formula}
      instanciada={instanciada}
      resultado={
        tieneValor
          ? regresion
            ? formatoEnUnidad(propia!.value as number)
            : formatoNumero(propia!.value as number, decimales)
          : "n/d"
      }
      resultadoEtiqueta={metricLabelPorTipo(metricKey, tipo)}
      umbralTexto={umbral ? textoUmbralRelativo(umbralTexto(umbral, regresion ? formatoEnUnidad : undefined), propia) : null}
      estado={tieneValor ? propia!.state : undefined}
      motivo={caps?.matriz === "kxk" || regresion ? motivoMulticlase(propia, tieneValor, regresion ? formatoEnUnidad : undefined) : undefined}
    />
  );
}

/**
 * Dos columnas de "Cómo se ha calculado": tabla a la izquierda,
 * fórmula -la pieza principal- a la derecha. `@container` propio: mide SU
 * ancho, así que en `/alertas/:id` y el panel lateral queda en una columna;
 * ahí la caja de fórmula va PRIMERO (`order-*`: desde `@lg` vuelve a
 * su sitio, tabla a la izquierda).
 */
export interface ColumnasCalculoProps {
  tabla: ReactNode;
  formula: ReactNode;
}

export function ColumnasCalculo({ tabla, formula }: ColumnasCalculoProps) {
  return (
    <div className="@container">
      <div className="grid gap-4 @lg:grid-cols-2 @lg:items-start">
        <div className="order-2 flex flex-col gap-3 @lg:order-1">{tabla}</div>
        <div className="order-1 flex flex-col gap-3 @lg:order-2">{formula}</div>
      </div>
    </div>
  );
}

export default FormulaInstanciada;
