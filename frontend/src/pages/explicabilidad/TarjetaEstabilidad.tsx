/**
 * Tarjeta «Estabilidad de la explicación»:
 * junto al gráfico «Línea base frente a ahora», dentro del bloque con ancla
 * `estado`, para que el dato del panel de la demo (pasos 9 y 20, que apuntan
 * a esa ancla con `metric_key: "explain_stability_ndcg"`) tenga la métrica
 * a la vista en la pantalla del paso.
 *
 * El detalle «Cómo se ha calculado» usa `CajaFormula` (`./CajaFormula.tsx`,
 * ya exportada por el barrel `components/vigia`): forma
 * única de todo cálculo con `formula` (caja con la fórmula simbólica arriba,
 * cifra instanciada, estado y umbral debajo). Antes la replicaba a mano y divergía (sin
 * `bg-muted/30` ni la partición negrita/tabular de la fórmula).
 *
 * El `StateBadge` de la cabecera (fuera de `<details>`) se mantiene aunque
 * `CajaFormula` traiga el suyo propio: con el detalle colapsado por
 * defecto —su estado inicial—, es el único estado a la vista, que es el
 * motivo de las dos frases. Mismo patrón que `TarjetaAmpliada` +
 * `CalculoMetricaAmpliada` en `pages/monitores/serie.tsx` y `calculo.tsx`:
 * badge de cabecera siempre visible y badge propio de `CajaFormula` en el
 * bloque de cálculo, a la vez, para la misma métrica. No es una
 * duplicación que corregir, es la forma establecida.
 */

import { CajaFormula, InfoTooltip, StateBadge } from "@/components/vigia";
import { textoComoSeLee, textoQueMide } from "@/components/vigia/AyudaTexto";
import { useContenidoMetricasPorTipo } from "@/api/queries-contenido";
import type { EstadoMotor } from "@/api/types";
import { formatoNumero } from "@/lib/metrics";

export interface TarjetaEstabilidadProps {
  stability: number | null;
  stabilityState: EstadoMotor | null;
}

const METRIC_KEY = "explain_stability_ndcg";
const ETIQUETA_POR_DEFECTO = "Estabilidad de la explicación";

export function TarjetaEstabilidad({ stability, stabilityState }: TarjetaEstabilidadProps) {
  // La ayuda sale resuelta por tipo (`ayudaPorTipo`): la explicación de un modelo multiclase es por clase.
  const ayudaQ = useContenidoMetricasPorTipo();
  const ayuda = ayudaQ.data?.[METRIC_KEY];
  const etiqueta = ayuda?.etiqueta ?? ETIQUETA_POR_DEFECTO;
  const umbral = ayuda?.umbral_por_defecto?.limite_inferior ?? null;
  const umbralTexto = umbral !== null ? `Umbral: mínimo ${formatoNumero(umbral, 2)}` : null;

  return (
    <div className="flex flex-col gap-3 rounded-lg border p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
          {etiqueta}
          <InfoTooltip
            titulo={etiqueta}
            queMide={textoQueMide(ayuda)}
            comoSeLee={textoComoSeLee(ayuda)}
            formula={ayuda?.formula}
          />
        </span>
        <StateBadge estado={stabilityState} size="sm" />
      </div>
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="text-2xl font-semibold tabular-nums">{formatoNumero(stability, 3)}</span>
        {umbralTexto ? <span className="text-md font-semibold text-muted-foreground">{umbralTexto}</span> : null}
      </div>
      <details className="flex flex-col gap-2">
        <summary className="cursor-pointer text-sm font-semibold select-none">Cómo se ha calculado</summary>
        {ayuda?.formula ? (
          <div className="mt-2">
            <CajaFormula
              formula={ayuda.formula}
              resultado={formatoNumero(stability, 3)}
              resultadoEtiqueta={etiqueta}
              umbralTexto={umbralTexto}
              estado={stabilityState}
            />
          </div>
        ) : null}
      </details>
    </div>
  );
}

export default TarjetaEstabilidad;
