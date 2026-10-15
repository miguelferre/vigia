/**
 * Bloques de `/monitores/equidad` en regresión. Dos
 * piezas que `index.tsx` monta con `caps.metricas === "regresion"`:
 *
 * - `AvisoRangoFavorable` (arriba): con rango, «Cuenta como favorable: de 40 a
 *   81 horas por semana»; sin rango, lo dice con el motivo y que las
 *   medidas de pertenencia no tienen valor.
 * - `EquidadRegresion` (bajo la rejilla): siempre el error por grupo, en
 *   barras con su `n`, la tabla de diferencias con sus umbrales y el violín de
 *   la predicción por grupo. Las medidas de pertenencia al rango, cuando hay
 *   rango, son las tarjetas de siempre de la rejilla.
 */

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorDeConsulta } from "@/components/vigia";
import { useGuionDemo } from "@/api/queries-contenido";
import { nombreReferencia, nombreSupervisado, useGroupContext } from "@/components/vigia/contexto-grupos";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { formatoMetrica, textoRangos } from "@/lib/metrics";

import { BarrasErrorPorGrupo } from "./BarrasErrorPorGrupo";
import { TablaDiferenciasError } from "./TablaDiferenciasError";
import { ViolinPrediccionGrupos } from "./ViolinPrediccionGrupos";
import { EQUIDAD_ERROR } from "./regresion-datos";
import {
  leerErrorPorGrupo,
  leerMotivoSinRango,
  leerPrediccionPorGrupo,
  MOTIVO_SIN_RANGO,
} from "./regresion-equidad-datos";
import { useEtiquetaMetrica } from "./usar-etiqueta-metrica";
import { useEvaluationDetail } from "./usarEvaluacion";

export interface EquidadRegresionProps {
  evaluationId: number | null;
  projectId: number;
}

export function AvisoRangoFavorable({ evaluationId, projectId }: EquidadRegresionProps) {
  const { caps, rangos, unidad, sinRango } = useTipoTarea(projectId);
  const detalleQ = useEvaluationDetail(caps?.metricas === "regresion" ? evaluationId : null);
  if (caps?.metricas !== "regresion") return null;
  if (!sinRango) {
    return (
      <p className="text-sm" data-testid="equidad-rango">
        <span className="font-semibold">Cuenta como favorable: {textoRangos(rangos, unidad)}.</span>{" "}
        <span className="text-muted-foreground">
          Las medidas de abajo comparan con qué frecuencia cada grupo recibe una predicción dentro de ese rango.
        </span>
      </p>
    );
  }
  const motivo = (detalleQ.data ? leerMotivoSinRango(detalleQ.data.result) : null) ?? MOTIVO_SIN_RANGO;
  const textoMotivo =
    motivo === MOTIVO_SIN_RANGO ? "Las medidas de pertenencia no tienen valor porque no hay rango favorable" : `Las medidas de pertenencia no tienen valor. Motivo: ${motivo}`;
  return (
    <p className="text-sm text-muted-foreground" data-testid="equidad-sin-rango">
      <span className="font-semibold text-foreground">Este modelo no tiene rango favorable.</span> {textoMotivo}. Las medidas que cuentan favorables (impacto dispar, paridad estadística, tasas de error y
      similares) no se calculan; la equidad compara el error de cada grupo. El rango favorable se fija en el alta o en
      la plantilla antes de congelar la línea base. Qué hacer: si la línea base ya está congelada, crea un modelo nuevo
      con rango favorable.
    </p>
  );
}

export function EquidadRegresion({ evaluationId, projectId }: EquidadRegresionProps) {
  const { caps, unidad } = useTipoTarea(projectId);
  const detalleQ = useEvaluationDetail(caps?.metricas === "regresion" ? evaluationId : null);
  const ctx = useGroupContext();
  const dominio = useGuionDemo().data?.dominio;
  const etiqueta = useEtiquetaMetrica(projectId);
  if (caps?.metricas !== "regresion") return null;

  const nombres = { unpriv: nombreSupervisado(ctx, dominio), priv: nombreReferencia(ctx, dominio) };
  const d = detalleQ.data;
  const filas = d ? leerErrorPorGrupo(d.result) : null;
  const violin = d ? leerPrediccionPorGrupo(d.result) : null;
  const diferencias = (d?.measurements ?? []).filter((m) => m.group_code === null && (EQUIDAD_ERROR as readonly string[]).includes(m.metric_key));
  const formato = (clave: string, v: number) => formatoMetrica(clave, v, unidad);

  return (
    <section id="equidad-regresion" className="flex scroll-mt-20 flex-col gap-4" data-testid="equidad-regresion">
      <div className="flex flex-col gap-0.5">
        <h3 className="text-md font-semibold">Error por grupo</h3>
        <span className="text-xs text-muted-foreground">
          La equidad de una regresión mira, sobre todo, si el modelo se equivoca más con un grupo que con otro y si se
          queda corto o se pasa con alguno.
        </span>
      </div>
      {evaluationId === null ? (
        <Card className="p-4">
          <p className="text-sm text-muted-foreground">Sin evaluación de equidad todavía: el error por grupo aparece con el primer lote con valor real.</p>
        </Card>
      ) : detalleQ.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : detalleQ.isError ? (
        <ErrorDeConsulta que="la evaluación" error={detalleQ.error} onReintentar={() => void detalleQ.refetch()} />
      ) : (
        <>
          {filas ? (
            <BarrasErrorPorGrupo filas={filas} nombres={nombres} unidad={unidad} />
          ) : (
            <p className="text-sm text-muted-foreground" data-testid="sin-error-por-grupo">
              Esta evaluación no trae el error por grupo: vuelve a evaluar el lote.
            </p>
          )}
          {diferencias.length > 0 ? (
            <TablaDiferenciasError medidas={diferencias} etiqueta={etiqueta} formato={formato} />
          ) : null}
          {violin ? (
            <div className="flex flex-col gap-2">
              <h4 className="text-sm font-semibold">Lo que predice el modelo en cada grupo</h4>
              <ViolinPrediccionGrupos grupos={violin} nombres={nombres} unidad={unidad} />
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

export default EquidadRegresion;
