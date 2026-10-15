/**
 * Tarjeta ampliada de una métrica en la rejilla de monitores: gráfica
 * grande con una línea por grupo, leyenda, banda de intervalo cuando solo hay
 * un grupo y, debajo, la hoja de métricas (`hoja-metricas.tsx`).
 *
 * Los datos ya vienen agrupados desde `rejilla.tsx` (una sola petición de
 * `/timeline` con todas las métricas del monitor): esta pieza no
 * pide nada a la API. El selector de métrica de la vista original
 * se conserva pero degradado a filtro: aquí solo cambia qué
 * serie ya cargada se muestra, no dispara ninguna petición nueva.
 */

import { useMemo } from "react";
import { Minimize2Icon } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";

import { ChartContainer } from "@/components/ui/chart";
import { InfoTooltip, StateBadge } from "@/components/vigia";
import { useContenidoMetricasPorTipo } from "@/api/queries-contenido";
import { escalaDeFechas, formatoEje } from "@/lib/fechas";

import { textoQueMide } from "@/components/vigia/AyudaTexto";
import { useGroupContext } from "@/components/vigia/contexto-grupos";
import { HojaMetricas } from "./hoja-metricas";
import { HojaPorClase } from "./hoja-por-clase";
import { useEtiquetaMetrica } from "./usar-etiqueta-metrica";
import { useFormatoSerie } from "./serie-formato";
import { combinarPorFecha, peorEstado } from "./tipos";
import type { FilaCombinada, SerieAgrupada, UmbralesMetrica } from "./tipos";
import { LeyendaUmbrales } from "./serie-leyenda";
import { crearPuntoEstado, etiquetaGrupo, lineasIntervalo, PuntoTooltipAmpliado, Selector } from "./serie-partes";
import { cambiosDeVersion, lineasCambioVersion } from "./serie-version";

const SIN_ETIQUETAS: ReadonlyMap<number, string> = new Map();
const COLORES = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)"];

export interface TarjetaAmpliadaProps {
  metrica: string;
  metricasDisponibles: string[];
  series: SerieAgrupada[];
  umbral: UmbralesMetrica;
  faseDeLote: Map<number, string>;
  /** `model_version_id -> etiqueta`: rotula la línea de cambio de versión. */
  etiquetasVersion?: ReadonlyMap<number, string>;
  onCambiarMetrica: (metrica: string) => void;
  onContraer: () => void;
  /** Medidas por clase de esta métrica, sin umbral; van en su propia hoja. */
  seriesPorClase?: SerieAgrupada[];
}

export function TarjetaAmpliada({
  metrica,
  metricasDisponibles,
  series,
  umbral,
  faseDeLote,
  etiquetasVersion = SIN_ETIQUETAS,
  onCambiarMetrica,
  onContraer,
  seriesPorClase = [],
}: TarjetaAmpliadaProps) {
  const filas = useMemo(() => combinarPorFecha(series), [series]);
  const cambios = useMemo(() => cambiosDeVersion(filas, etiquetasVersion), [filas, etiquetasVersion]);
  // Con una tirada de demo, las nueve evaluaciones caen en el mismo día y un
  // eje `dd/mm/aaaa` repetiría la misma etiqueta en todas las marcas.
  const escalaEje = useMemo(() => escalaDeFechas(filas.map((f) => f.ts)), [filas]);
  const estado = peorEstado(series) ?? "sin_datos";
  // Con un solo grupo (el caso normal de calidad y deriva) se dibuja además
  // la banda de intervalo; con varios (equidad) la leyenda de líneas ya basta
  // y una banda por grupo saturaría la gráfica (la hoja de abajo trae el
  // intervalo de cada uno igualmente).
  const grupoUnico = series.length === 1 ? series[0]!.grupo : null;
  // Ayuda contextual: degrada a la etiqueta sola si `content/` no responde todavía.
  const ayudaQ = useContenidoMetricasPorTipo();
  const metricLabel = useEtiquetaMetrica();
  const ayuda = ayudaQ.data?.[metrica];
  // `group_context` del monitor: nombra el grupo en la leyenda y el tooltip.
  const groupContext = useGroupContext();
  // En regresión el valor, el tooltip y los límites llevan la unidad (`serie-formato.ts`).
  const { formatoValor, formatoLimite, ejeEnUnidad } = useFormatoSerie(metrica);

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          {/* Título de menos protagonismo: lo que importa aquí es poder
              reducir la gráfica, no repetir el nombre de la métrica. */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">{metricLabel(metrica)}</span>
            <StateBadge estado={estado} size="sm" />
            <InfoTooltip titulo={metricLabel(metrica)} queMide={textoQueMide(ayuda)} formula={ayuda?.formula} />
          </div>
          <button
            type="button"
            aria-expanded={true}
            aria-label="Reducir la gráfica ampliada"
            onClick={onContraer}
            className="inline-flex w-fit items-center gap-1.5 rounded px-2 py-1 text-sm font-semibold hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Minimize2Icon className="size-4" aria-hidden="true" />
            Reducir
          </button>
        </div>
        <Selector
          etiqueta="Filtrar métrica"
          valor={metrica}
          opciones={metricasDisponibles}
          onCambio={onCambiarMetrica}
          etiquetaOpcion={metricLabel}
        />
      </div>

      {filas.length === 0 ? (
        <p className="text-sm text-muted-foreground">No hay evaluaciones con esta métrica todavía.</p>
      ) : (
        <>
          {ejeEnUnidad ? (
            <p className="text-xs text-muted-foreground" data-testid="eje-unidad">
              Eje vertical en {ejeEnUnidad}.
            </p>
          ) : null}
          <ChartContainer config={{ valor: { label: metricLabel(metrica), color: "var(--chart-1)" } }} className="h-80">
            <LineChart data={filas} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="ts"
                tickFormatter={(v: string) => formatoEje(v, escalaEje)}
                stroke="var(--muted-foreground)"
                fontSize={11}
                interval="preserveStartEnd"
              />
              <YAxis stroke="var(--muted-foreground)" fontSize={11} width={56} />
              <Tooltip
                content={<PuntoTooltipAmpliado faseDeLote={faseDeLote} groupContext={groupContext} formatoValor={formatoValor} />}
              />
              {series.length > 1 ? (
                <Legend
                  formatter={(valor: string) => etiquetaGrupo(valor, groupContext)}
                  wrapperStyle={{ fontSize: 11 }}
                />
              ) : null}
              {lineasCambioVersion(cambios)}
              {umbral.low !== null ? (
                <ReferenceLine y={umbral.low} stroke="var(--state-warn)" strokeWidth={2} strokeDasharray="6 4" />
              ) : null}
              {umbral.high !== null ? (
                <ReferenceLine y={umbral.high} stroke="var(--state-alert)" strokeWidth={2} strokeDasharray="6 4" />
              ) : null}
              {lineasIntervalo(grupoUnico)}
              {series.map((s, i) => (
                <Line
                  key={s.grupo}
                  dataKey={(f: FilaCombinada) => f.porGrupo[s.grupo]?.value ?? null}
                  name={s.grupo}
                  stroke={COLORES[i % COLORES.length]}
                  // La línea de las gráficas ampliadas y la del umbral van algo más gruesas.
                  strokeWidth={3}
                  dot={crearPuntoEstado(s.grupo)}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ChartContainer>

          <LeyendaUmbrales
            umbral={umbral}
            hayCambioVersion={cambios.length > 0}
            formatoLimite={formatoLimite}
          />

          <div className="flex flex-col gap-2">
            <h3 className="text-sm text-muted-foreground">Medidas por grupo</h3>
            <HojaMetricas metrica={metrica} series={series} />
          </div>

          {seriesPorClase.length > 0 ? (
            <div className="flex flex-col gap-2">
              <h3 className="text-sm text-muted-foreground">Medidas por clase</h3>
              <HojaPorClase metrica={metrica} series={seriesPorClase} />
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
