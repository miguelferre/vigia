/**
 * Estado de la explicabilidad al abrir `/explicabilidad`:
 * «Línea base frente a ahora», un dumbbell por
 * variable del top 10 actual de la última explicación global de la versión
 * activa, con `nombreVariable`, más las frases calculadas de `ranking_delta`
 * y `stability` (orden y pesos, en dos párrafos) y la
 * tarjeta de estabilidad (`TarjetaEstabilidad.tsx`). Aparte de `index.tsx`
 * para no crecer de más; las filas del dumbbell viven en
 * `ranking-comparado-datos.ts`, las frases en `frase-comparada.ts` y el
 * dibujo en `RankingComparado.tsx`.
 */

import { useMemo } from "react";
import { InfoIcon } from "lucide-react";
import { Link, useNavigate } from "react-router";

import { useGuionDemo } from "@/api/queries-contenido";
import type { Explanation, ProjectDetail } from "@/api/types";
import type { ExplanationSummary } from "@/api/types-domain";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatoFecha } from "@/lib/metrics";
import { fraseComparada } from "./frase-comparada";
import { extraerFilas, prepararFilasComparadas } from "./ranking-comparado-datos";
import { RankingComparado } from "./RankingComparado";
import { crearTooltipRegresion, formatoImportancia, LecturaRegresion, tituloEjeRegresion } from "./explicacion-regresion";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { RankingBarrasFijo } from "./ranking-barras-fijo";
import { TarjetaEstabilidad } from "./TarjetaEstabilidad";
import { TooltipBarra } from "./TooltipBarra";

export interface EstadoExplicabilidadProps {
  proyecto: ProjectDetail | undefined;
  batchesCargando: boolean;
  hayLotes: boolean;
  lista: Explanation[];
  resumen: ExplanationSummary | undefined;
  onVer: (id: number) => void;
}

export function EstadoExplicabilidad({
  proyecto,
  batchesCargando,
  hayLotes,
  lista,
  resumen,
  onVer,
}: EstadoExplicabilidadProps) {
  const dominio = useGuionDemo().data?.dominio;
  const navegar = useNavigate();
  // En regresión las importancias van en la unidad de la salida.
  const tarea = useTipoTarea(proyecto?.id ?? null);
  const regresion = tarea.caps?.metricas === "regresion";
  const unidad = tarea.unidad;
  const tooltip = useMemo(() => (regresion ? crearTooltipRegresion(unidad, false) : TooltipBarra), [regresion, unidad]);
  const formatoPeso = useMemo(
    () => (regresion ? (valor: number) => formatoImportancia(valor, unidad) : undefined),
    [regresion, unidad],
  );
  const ultimaGlobal = lista.find((e) => e.kind !== "local_lime" && e.available);

  if (!ultimaGlobal) {
    const versionActiva = proyecto?.versions.find((v) => v.is_active);
    // Sin artefacto subido, `check_explainable` da 409 antes de intentar
    // nada; en vez de dejar que ese error asome aquí, se dice dónde subirlo
    // (versionActiva.model_kind es "external_files" hasta que la subida lo
    // pasa a "executable"; sim_logistic, el simulador, nunca lo necesita).
    const sinArtefacto = !!versionActiva && versionActiva.model_kind !== "sim_logistic" && !versionActiva.artifact_sha256;
    const motivo = sinArtefacto
      ? null
      : proyecto?.store_features === false
        ? "La explicabilidad está desactivada para este despliegue («Guardar las variables de entrada de cada registro», en Configuración)."
        : proyecto?.explain_auto === false
          ? "La explicación automática está desactivada; lánzala a mano abajo, o actívala en Configuración."
          : batchesCargando
            ? "Cargando…"
            : !hayLotes
              ? "Todavía no se ha evaluado ningún lote de esta versión."
              : "El cálculo automático no ha terminado todavía; puede tardar unos minutos tras el último lote.";
    return (
      <Alert id="estado" className="scroll-mt-20">
        <InfoIcon />
        <AlertTitle>Sin explicaciones todavía</AlertTitle>
        <AlertDescription>
          {sinArtefacto ? (
            <span>
              El fichero del modelo (ONNX) es opcional: sin él solo se pierde la explicabilidad, y la
              deriva, la equidad y la calidad se vigilan igual. Si quieres explicaciones, súbelo en{" "}
              {proyecto ? (
                <Link className="text-link hover:underline" to={`/modelos/${proyecto.id}#versiones`}>
                  Modelos · {proyecto.name} · Versiones
                </Link>
              ) : (
                "Modelos · Versiones"
              )}
              .
            </span>
          ) : (
            motivo
          )}
        </AlertDescription>
      </Alert>
    );
  }

  const filas = extraerFilas(ultimaGlobal.result, dominio);
  const referenciaTop = resumen?.reference_top_features ?? null;
  const filasComparadas =
    filas.length > 0 && referenciaTop
      ? prepararFilasComparadas(filas, ultimaGlobal.result, referenciaTop, resumen?.ranking_delta ?? [], dominio)
      : null;
  // La frase única de antes se parte en dos (orden y pesos), una tarjeta
  // de estabilidad aparte (`TarjetaEstabilidad`, más abajo) y un párrafo cada una.
  const frases =
    filasComparadas !== null
      ? fraseComparada(
          resumen?.ranking_delta ?? [],
          filasComparadas,
          resumen?.stability ?? null,
          resumen?.stability_state ?? null,
          dominio,
          formatoPeso,
        )
      : null;

  return (
    <Card id="estado" className="scroll-mt-20">
      <CardHeader>
        <CardTitle className="text-md">Línea base frente a ahora</CardTitle>
        <p className="text-xs text-muted-foreground">
          Calculado el {formatoFecha(ultimaGlobal.created_at)}.{" "}
          {frases ? frases.orden : "Sin explicación de referencia todavía."}
        </p>
        {frases ? <p className="text-xs text-muted-foreground">{frases.pesos}</p> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <TarjetaEstabilidad stability={resumen?.stability ?? null} stabilityState={resumen?.stability_state ?? null} />
        {regresion ? <LecturaRegresion kind={ultimaGlobal.kind} unidad={unidad} predicho={null} /> : null}
        {filas.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin importancias en el resultado.</p>
        ) : filasComparadas !== null ? (
          <>
            <RankingComparado
              filas={filasComparadas}
              formato={formatoPeso}
              tituloEje={regresion ? tituloEjeRegresion(ultimaGlobal.kind, unidad) : undefined}
              onClickFila={(featureTecnico) => navegar(`/monitores/deriva?variable=${encodeURIComponent(featureTecnico)}`)}
            />
            <p className="text-xs text-muted-foreground">Clic en una variable para ver su distribución en deriva</p>
          </>
        ) : (
          <>
            <RankingBarrasFijo
              datos={filas}
              etiqueta={formatoPeso}
              claveCategoria="feature"
              claveValor="valor"
              tooltip={tooltip}
              color={() => "var(--chart-1)"}
              onClickBarra={(fila) => navegar(`/monitores/deriva?variable=${encodeURIComponent(fila.featureTecnico)}`)}
            />
            <p className="text-xs text-muted-foreground">Clic en una variable para ver su distribución en deriva</p>
          </>
        )}
        <button
          type="button"
          className="w-fit text-xs text-link hover:underline"
          onClick={() => {
            if (ultimaGlobal.id != null) onVer(ultimaGlobal.id);
          }}
        >
          Ver el detalle completo
        </button>
      </CardContent>
    </Card>
  );
}

export default EstadoExplicabilidad;
