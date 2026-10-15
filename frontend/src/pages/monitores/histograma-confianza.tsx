/**
 * Histograma de confianza del modelo, línea base frente a lote:
 * forma B del componente compartido `HistogramaBaseLote`
 * sobre `result.details.confidence` de una evaluación de deriva. Sustituye el
 * histograma superpuesto de antes.
 *
 * Fuente: `core/drift.py:confidence_drift`: `bin_edges`
 * (bordes, un elemento más que las barras), `bin_counts_base` y
 * `bin_counts_actual`, más `psi`/`ks_stat`/`ks_p`/`jensen_shannon_distance`.
 * Se normaliza a porcentaje de cada ventana: `n` base y lote no coinciden.
 *
 * Props: `sinTitulo` omite la cabecera propia
 * (título e ⓘ) cuando la tarjeta que lo monta ya los pinta (bloque
 * «Distribuciones»); sin él, la cabecera es la de siempre. Ancla de
 * onboarding: `histograma-confianza` (destino de la escena 6), siempre en la
 * raíz tanto con título como sin él.
 *
 * Selector de clase predicha: con
 * `details.confidence.by_class` (`confianza-por-clase.ts`,
 * `selector-clase-confianza.tsx`) añade «Todas · Derivar · No derivar»
 * sobre el histograma y la frase calculada del umbral fijo de lectura; sin
 * `by_class` (evaluación anterior) el selector no aparece y el
 * comportamiento es el de siempre. `dominio`/`favorableLabel` (opcionales,
 * los pasa `DistribucionesDeriva.tsx`): nombran las clases del proyecto; sin
 * ellos, nombres genéricos.
 */

import { useState } from "react";

import {
  HistogramaBaseLote,
  InfoTooltip,
  construirFilasHistograma,
  etiquetasDeBordes,
  fraseTramosQueMasCambian,
  distribucionesIdenticas,
} from "@/components/vigia";
import { useContenidoMetricasPorTipo } from "@/api/queries-contenido";
import { Skeleton } from "@/components/ui/skeleton";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import type { EvaluationDetail, JsonObject } from "@/api/types";
import { formatoNumero, metricLabel } from "@/lib/metrics";

import { textoComoSeLee, textoQueMide } from "@/components/vigia/AyudaTexto";
import {
  estadisticosPorSeleccion,
  extraerConfianzaPorClase,
  nombreClasePredicha,
  opcionesClasesConfianza,
  type OpcionClase,
  fraseUmbralConfianza,
  seriePorSeleccion,
  type SeleccionClase,
} from "./confianza-por-clase";
import { SelectorClaseConfianza } from "./selector-clase-confianza";
import { FilaEstadisticosConfianza } from "./histograma-confianza-estadisticos";
import { extraerConfianza } from "./histograma-confianza-datos";

/* ---------- componente ---------- */

export interface HistogramaConfianzaProps {
  evaluacion: EvaluationDetail;
  /** Omite la cabecera propia (título e ⓘ): la tarjeta que lo monta ya los pinta. */
  sinTitulo?: boolean;
  /** Dominio del proyecto: nombra las clases si es de derivación. Sin él, nombres genéricos. */
  dominio?: string | null;
  /** Clase favorable del proyecto: sin ella, nombres genéricos. */
  favorableLabel?: number | null;
}

export function HistogramaConfianza({ evaluacion, sinTitulo, dominio, favorableLabel }: HistogramaConfianzaProps) {
  const details = (evaluacion.result?.details as JsonObject | undefined) ?? null;
  const confianza = extraerConfianza(details);
  // Multiclase = `k` claves de texto en `by_class` y confianza en [1/k, 1];
  // binario = «1» y «0» y [0,5; 1], como siempre.
  const { caps, clases, favorables } = useTipoTarea(evaluacion.project_id);
  const multiclase = caps?.confianza === "por_clase";
  const porClase = extraerConfianzaPorClase(details, multiclase ? null : ["1", "0"]);
  const opciones: OpcionClase[] =
    porClase === null
      ? []
      : multiclase
        ? opcionesClasesConfianza(porClase, clases, favorables)
        : [
            { valor: "1", etiqueta: nombreClasePredicha(dominio, 1, favorableLabel) },
            { valor: "0", etiqueta: nombreClasePredicha(dominio, 0, favorableLabel) },
          ];
  const [seleccion, setSeleccion] = useState<SeleccionClase>("todas");
  // Sin `by_class` la selección efectiva es siempre "todas", aunque el estado interno quedara en otra.
  const seleccionValida: SeleccionClase = porClase ? seleccion : "todas";
  const { base: serieBase, actual: serieActual } = seriePorSeleccion(seleccionValida, confianza, porClase);
  const tramos = confianza ? etiquetasDeBordes(confianza.binEdges) : [];
  const filas = confianza ? construirFilasHistograma(tramos, serieBase, serieActual) : [];
  const sinBins = !confianza || filas.length === 0;
  const nBase = serieBase.reduce((a, b) => a + b, 0);
  const nActual = serieActual.reduce((a, b) => a + b, 0);
  const fraseUmbral = confianza && porClase ? fraseUmbralConfianza(confianza.binEdges, serieBase, serieActual) : null;
  // Los estadísticos de la fila son los de la pestaña activa
  // (Derivar/No derivar), no siempre los globales.
  const estadisticos = estadisticosPorSeleccion(seleccionValida, confianza, porClase);
  const ayudaQ = useContenidoMetricasPorTipo(evaluacion.project_id);
  const ayuda = ayudaQ.data?.confidence_drift_score;

  const frase = sinBins
    ? null
    : distribucionesIdenticas(filas)
      ? `Las dos distribuciones son idénticas: la línea base y el lote reparten los ${filas.length} tramos por igual.`
      : fraseTramosQueMasCambian(filas, 3);

  // Con el proyecto cargando no se dibuja binario por defecto.
  if (!caps) return <Skeleton id="histograma-confianza" className="h-56 w-full" />;

  return (
    <div id="histograma-confianza" className="flex flex-col gap-3">
      {sinTitulo ? null : (
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold">Distribución de confianza: línea base frente a lote</h4>
          <InfoTooltip
            titulo={metricLabel("confidence_drift_score")}
            queMide={textoQueMide(
              ayuda,
              "Cuánto se ha movido la confianza de la predicción (la probabilidad de la clase más probable) entre la línea base y el lote.",
            )}
            comoSeLee={textoComoSeLee(ayuda)}
            formula={ayuda?.formula}
          />
        </div>
      )}

      {sinBins ? (
        <p className="text-sm text-muted-foreground">Sin datos de confianza en esta evaluación.</p>
      ) : (
        <>
          {porClase ? (
            <SelectorClaseConfianza seleccion={seleccionValida} onSeleccion={setSeleccion} opciones={opciones} />
          ) : null}
          <HistogramaBaseLote
            tramos={tramos}
            base={serieBase}
            actual={serieActual}
            prefijoTramo="Confianza"
            alto={220}
            tituloEjeX={`Confianza del modelo en su decisión, de ${multiclase ? formatoNumero(confianza?.binEdges[0] ?? 0.5, 2) : "0,5"} a 1`}
            tituloEjeY="% de registros de la ventana"
          />
          {/* Frase calculada del umbral fijo de lectura, sobre el n de la selección. */}
          {fraseUmbral ? (
            <p className="text-xs font-medium text-foreground" data-frase-confianza={seleccion}>
              {fraseUmbral}
            </p>
          ) : null}
          {/* Qué es la confianza, antes de la lectura del
              gráfico, sin duplicarla. */}
          {multiclase ? (
            <p className="text-xs text-muted-foreground">
              La confianza es la probabilidad que el modelo da a la clase que predice. Con {clases.length || "k"} clases,{" "}
              {formatoNumero(confianza?.binEdges[0] ?? 0, 2)} es repartir la probabilidad por igual entre todas (sin
              ninguna preferida) y 1 es seguridad total.
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              La confianza es la probabilidad que el modelo da a la clase que predice, sea la favorable o no:
              0,5 es una moneda al aire, 1 es seguridad total.
            </p>
          )}
          {/* Lectura del gráfico bajo el propio histograma, sin repetir la
              leyenda de colores que ya pinta `HistogramaBaseLote`. */}
          <p className="text-xs text-muted-foreground">
            Cuanto más a la derecha, más seguro está el modelo de su predicción; la línea base es el
            escalón y el lote las barras.
          </p>
          <FilaEstadisticosConfianza
            psi={estadisticos.psi}
            ksStat={estadisticos.ksStat}
            ksP={estadisticos.ksP}
            jsDistance={estadisticos.jsDistance}
            nBase={nBase}
            nActual={nActual}
          />
          {frase ? <p className="text-xs text-muted-foreground">{frase}</p> : null}
        </>
      )}
    </div>
  );
}

export default HistogramaConfianza;
