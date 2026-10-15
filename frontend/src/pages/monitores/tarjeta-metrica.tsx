/**
 * Tarjeta contraída de una métrica en la rejilla.
 *
 * Envuelve `KpiCard` (frontera de la sesión: no se toca) sin pasarle
 * `onClick`, para llevar el `aria-expanded` y el foco visible en un botón
 * propio en vez del que monta `KpiCard` por dentro.
 */

import { InfoTooltip, KpiCard, StateBadge } from "@/components/vigia";
import type { PuntoSerie } from "@/components/vigia";
import { useContenidoMetricasPorTipo } from "@/api/queries-contenido";

import { textoComoSeLee, textoQueMide } from "@/components/vigia/AyudaTexto";
import { useFormatoMetrica } from "@/components/vigia/useFormatoMetrica";
import { GRUPO_GLOBAL, peorEstado, serieRepresentativa } from "./tipos";
import type { SerieAgrupada, UmbralesMetrica } from "./tipos";
import { useEtiquetaMetrica } from "./usar-etiqueta-metrica";

export interface TarjetaMetricaProps {
  metrica: string;
  series: SerieAgrupada[];
  umbral: UmbralesMetrica;
  onExpandir: () => void;
  /**
   * Con una métrica ampliada en la rejilla, las demás se minimizan a
   * una cabecera (nombre, valor actual, estado, sin gráfica) para dejar sitio
   * al cálculo pegado a la gráfica ampliada.
   */
  minimizada?: boolean;
  /** En multiclase, una medida sin umbral se llama «Sin umbral», no «Correcto». */
  multiclase?: boolean;
}

export function TarjetaMetrica({ metrica, series, umbral, onExpandir, minimizada, multiclase }: TarjetaMetricaProps) {
  const metricLabel = useEtiquetaMetrica();
  const representativa = serieRepresentativa(series);
  const ultimo = representativa?.puntos[representativa.puntos.length - 1] ?? null;
  // Las medidas de error de regresión llevan su unidad; el resto sale como siempre.
  const { formato, partes } = useFormatoMetrica();
  const valorPartes = partes(metrica, ultimo?.value);
  const estadoSerie = peorEstado(series) ?? "sin_datos";
  // Multiclase: la medida sin umbral evaluado (el motor la publica en `ok` sin límite) no es
  // «Correcto»: nadie la ha comparado con nada. Se enseña neutra y con ese nombre.
  const sinUmbral =
    multiclase === true &&
    estadoSerie === "ok" &&
    ultimo !== null &&
    ultimo.threshold_low === null &&
    ultimo.threshold_high === null;
  const estado = sinUmbral ? "sin_datos" : estadoSerie;
  const textoEstado = sinUmbral ? "Sin umbral" : undefined;
  const serieSpark: PuntoSerie[] = (representativa?.puntos ?? []).map((p) => ({
    ts: p.ts,
    valor: p.value,
    estado: p.state,
  }));
  // Un solo grupo ya lo dice el título (o la descripción, si no es "global");
  // el desglose de la tarjeta solo aporta con más de uno.
  const conGrupos = series.length > 1;
  // Ayuda contextual: si `content/` todavía no responde, se degrada
  // a la etiqueta sin qué-mide ni fórmula (ver InfoTooltip más abajo).
  const ayudaQ = useContenidoMetricasPorTipo();
  const ayuda = ayudaQ.data?.[metrica];

  if (minimizada) {
    return (
      <div
        role="button"
        tabIndex={0}
        aria-expanded={false}
        aria-label={`Ampliar ${metricLabel(metrica)}`}
        onClick={onExpandir}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onExpandir();
          }
        }}
        className="flex w-full cursor-pointer items-center justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2.5 text-left hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="inline-flex items-center gap-1.5 text-sm font-medium">
          {metricLabel(metrica)}
          <span onClick={(e) => e.stopPropagation()}>
            <InfoTooltip
              titulo={metricLabel(metrica)}
              queMide={textoQueMide(ayuda)}
              comoSeLee={textoComoSeLee(ayuda)}
              formula={ayuda?.formula}
            />
          </span>
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="text-sm font-semibold tabular-nums">{ultimo ? formato(metrica, ultimo.value) : "n/d"}</span>
          <StateBadge estado={estado} texto={textoEstado} size="sm" />
        </span>
      </div>
    );
  }

  return (
    // `div role="button"` y no `<button>`: el ⓘ de dentro es también un botón
    // (InfoTooltip) y HTML no admite botones anidados. El teclado se cubre a
    // mano (Enter/espacio) igual que lo haría un `<button>` nativo.
    <div
      role="button"
      tabIndex={0}
      aria-expanded={false}
      aria-label={`Ampliar ${metricLabel(metrica)}`}
      onClick={onExpandir}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onExpandir();
        }
      }}
      className="block w-full cursor-pointer rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <KpiCard
        titulo={metricLabel(metrica)}
        // El ⓘ va a la derecha del valor grande, no debajo: se pasa
        // dentro de `valor`, que `KpiCard` acepta como `ReactNode`.
        valor={
          <span className="inline-flex items-center gap-1.5">
            {valorPartes.numero}
            {valorPartes.unidad ? (
              <span className="text-sm font-normal text-muted-foreground">{valorPartes.unidad}</span>
            ) : null}
            <span onClick={(e) => e.stopPropagation()}>
              <InfoTooltip
                titulo={metricLabel(metrica)}
                queMide={textoQueMide(ayuda)}
                comoSeLee={textoComoSeLee(ayuda)}
                formula={ayuda?.formula}
              />
            </span>
          </span>
        }
        estado={estado}
        textoEstado={textoEstado}
        serie={serieSpark}
        umbrales={{ bajo: umbral.low, alto: umbral.high }}
        formatoValor={(v) => formato(metrica, v)}
        descripcion={
          representativa && representativa.grupo !== GRUPO_GLOBAL ? `Grupo ${representativa.grupo}` : undefined
        }
        pie={
          conGrupos ? (
            <div className="flex flex-wrap gap-1">
              {series.map((s) => (
                <StateBadge
                  key={s.grupo}
                  estado={s.puntos[s.puntos.length - 1]?.state ?? "sin_datos"}
                  size="sm"
                  texto={s.grupo === GRUPO_GLOBAL ? "Global" : s.grupo}
                />
              ))}
            </div>
          ) : undefined
        }
      />
    </div>
  );
}
