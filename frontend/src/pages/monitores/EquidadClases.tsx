/**
 * Bloque de multiclase de `/monitores/equidad`:
 *
 * - Dice qué clases cuentan como resultado favorable («Cuentan como resultado
 *   favorable: A, B»). Las medidas de equidad son las de siempre sobre esa
 *   pertenencia: el 0/1 de «cae en una clase favorable».
 * - Enseña, plegada, la tabla `details.fairness.por_clase`: la tasa con que se
 *   predice cada clase en cada grupo, su razón y el `n` de cada celda. Es
 *   informativa: no tiene umbral ni abre alertas.
 * - Sin conjunto favorable, lo dice: la equidad solo compara la
 *   exactitud y la F1 macro de cada grupo, sin umbral.
 *
 * Solo se monta en multiclase (`caps.favorables === "conjunto"`).
 */

import { useGuionDemo } from "@/api/queries-contenido";
import type { EvaluationDetail } from "@/api/types";
import { nombreReferencia, nombreSupervisado, useGroupContext } from "@/components/vigia/contexto-grupos";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { formatoCorto } from "@/lib/metrics";
import { claveClase } from "@/lib/tipo-tarea";

import { useEvaluationDetail } from "./usarEvaluacion";

type Obj = Record<string, unknown>;

const esObjeto = (v: unknown): v is Obj => v !== null && typeof v === "object" && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

interface Celda {
  n: number | null;
  nClase: number | null;
  tasa: number | null;
}

interface FilaClase {
  clase: string;
  supervisado: Celda;
  referencia: Celda;
  razon: number | null;
}

function leerCelda(v: unknown): Celda {
  return esObjeto(v) ? { n: num(v.n), nClase: num(v.n_clase), tasa: num(v.tasa) } : { n: null, nClase: null, tasa: null };
}

function leerPorClase(result: EvaluationDetail["result"]): FilaClase[] {
  const details = esObjeto(result) ? result.details : null;
  const fairness = esObjeto(details) ? details.fairness : null;
  const porClase = esObjeto(fairness) ? fairness.por_clase : null;
  if (!esObjeto(porClase)) return [];
  return Object.entries(porClase).flatMap(([claseCruda, v]) =>
    esObjeto(v) ? [{ clase: claveClase(claseCruda), supervisado: leerCelda(v.unpriv), referencia: leerCelda(v.priv), razon: num(v.razon) }] : [],
  );
}

function CeldaTasa({ c }: { c: Celda }) {
  if (c.tasa === null) {
    return (
      <span className="flex flex-col items-end">
        <span className="text-muted-foreground">sin datos</span>
        {c.n !== null ? <span className="text-[10px] text-muted-foreground">n = {c.n.toLocaleString("es-ES")}</span> : null}
      </span>
    );
  }
  return (
    <span className="flex flex-col items-end">
      <span>{formatoCorto(c.tasa * 100, 1)} %</span>
      {c.n !== null && c.nClase !== null ? (
        <span className="text-[10px] text-muted-foreground">
          {c.nClase.toLocaleString("es-ES")} de {c.n.toLocaleString("es-ES")}
        </span>
      ) : null}
    </span>
  );
}

export interface EquidadClasesProps {
  evaluationId: number | null;
  projectId: number;
}

export function EquidadClases({ evaluationId, projectId }: EquidadClasesProps) {
  const { caps, favorables, clases } = useTipoTarea(projectId);
  const detalleQ = useEvaluationDetail(evaluationId);
  const ctx = useGroupContext();
  const dominio = useGuionDemo().data?.dominio;
  if (caps?.favorables !== "conjunto") return null;

  const filas = detalleQ.data ? leerPorClase(detalleQ.data.result) : [];
  const orden = (c: string) => {
    const i = clases.indexOf(c);
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  filas.sort((a, b) => orden(a.clase) - orden(b.clase));
  const supervisado = nombreSupervisado(ctx, dominio);
  const referencia = nombreReferencia(ctx, dominio);
  const th = "sticky top-0 border-b bg-card px-3 py-1.5 text-right font-medium text-muted-foreground";

  return (
    <section id="equidad-clases" className="flex flex-col gap-2" data-testid="equidad-clases">
      {favorables.length > 0 ? (
        <p className="text-sm" data-testid="favorables-texto">
          <span className="font-semibold">Cuentan como resultado favorable: {favorables.join(", ")}.</span>{" "}
          <span className="text-muted-foreground">
            Las medidas de equidad comparan con qué frecuencia cada grupo recibe alguna de esas clases frente a
            cualquier otra.
          </span>
        </p>
      ) : (
        <p className="text-sm text-muted-foreground" data-testid="favorables-texto">
          <span className="font-semibold text-foreground">Este modelo no tiene clases favorables.</span> La equidad solo
          compara la exactitud y la F1 macro de cada grupo, sin umbral.
        </p>
      )}
      {filas.length > 0 ? (
        <details className="text-sm" data-testid="equidad-por-clase">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
            Predicción de cada clase por grupo ({filas.length} clases, informativa)
          </summary>
          <div className="mt-2 flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">
              Con qué frecuencia el modelo predice cada clase en cada grupo, la razón entre los dos grupos y cuántos
              casos hay en cada celda. No tiene umbral y no abre alertas; la celda de un grupo con muy pocos casos no
              da tasa.
            </p>
            <div
              role="region"
              tabIndex={0}
              aria-label="Predicción de cada clase por grupo"
              className="max-h-80 max-w-full overflow-auto rounded-lg border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <table className="w-max min-w-full border-separate border-spacing-0 text-sm">
                <thead>
                  <tr>
                    <th className={`${th} left-0 z-10 text-left`}>Clase</th>
                    <th className={th}>{supervisado}</th>
                    <th className={th}>{referencia}</th>
                    <th className={th}>Razón</th>
                  </tr>
                </thead>
                <tbody>
                  {filas.map((f) => (
                    <tr key={f.clase}>
                      <th
                        scope="row"
                        className="sticky left-0 max-w-44 whitespace-normal border-b bg-card px-3 py-1.5 text-left font-normal [overflow-wrap:anywhere] sm:max-w-72"
                      >
                        {f.clase}
                        {favorables.includes(f.clase) ? <span className="text-muted-foreground"> (favorable)</span> : null}
                      </th>
                      <td className="border-b px-3 py-1.5 text-right tabular-nums">
                        <CeldaTasa c={f.supervisado} />
                      </td>
                      <td className="border-b px-3 py-1.5 text-right tabular-nums">
                        <CeldaTasa c={f.referencia} />
                      </td>
                      <td className="border-b px-3 py-1.5 text-right tabular-nums">
                        {f.razon === null ? <span className="text-muted-foreground">n/d</span> : formatoCorto(f.razon, 2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </details>
      ) : null}
    </section>
  );
}

export default EquidadClases;
