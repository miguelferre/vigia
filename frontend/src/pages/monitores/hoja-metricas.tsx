/**
 * Hoja de métricas: medidas por grupo de la tarjeta ampliada, con
 * valor, intervalo, umbral y estado, tal como los trae el último punto de
 * `/timeline` de cada grupo. `components/ui/table.tsx` estaba huérfano
 * (esta pieza lo usa).
 */

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { InfoTooltip, StateBadge } from "@/components/vigia";
import { decimalesDe } from "@/components/vigia/CalculoFormula";
import { useContenidoMetricasPorTipo } from "@/api/queries-contenido";
import { useFormatoMetrica } from "@/components/vigia/useFormatoMetrica";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { formatoNumero } from "@/lib/metrics";

import { textoComoSeLee, textoQueMide } from "@/components/vigia/AyudaTexto";
import { useGroupContext } from "@/components/vigia/contexto-grupos";
import { ultimosPorGrupo, type SerieAgrupada } from "./tipos";
import { etiquetaGrupo } from "./serie-partes";
import { useEtiquetaMetrica } from "./usar-etiqueta-metrica";

export interface HojaMetricasProps {
  /** Métrica de la que es esta hoja, para el ⓘ de la columna Valor. */
  metrica: string;
  series: SerieAgrupada[];
}

export function HojaMetricas({ metrica, series }: HojaMetricasProps) {
  const filas = ultimosPorGrupo(series);
  // Ayuda contextual: degrada a la etiqueta sola si `content/` no responde todavía.
  const ayudaQ = useContenidoMetricasPorTipo();
  const metricLabel = useEtiquetaMetrica();
  const ayuda = ayudaQ.data?.[metrica];
  // `group_context` del monitor: nombra el grupo en vez de su código.
  const groupContext = useGroupContext();
  // En regresión todo valor sale con `formatoMetrica` (unidad, signo); lo demás, como siempre.
  const { caps } = useTipoTarea();
  const { formato } = useFormatoMetrica();
  const regresion = caps?.metricas === "regresion";

  if (filas.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin medidas todavía para esta métrica.</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Grupo</TableHead>
          <TableHead>
            <span className="flex items-center gap-1.5">
              Valor
              <InfoTooltip
                titulo={metricLabel(metrica)}
                queMide={textoQueMide(ayuda)}
                comoSeLee={textoComoSeLee(ayuda)}
                formula={ayuda?.formula}
              />
            </span>
          </TableHead>
          <TableHead>Intervalo</TableHead>
          <TableHead>Umbral</TableHead>
          <TableHead>Estado</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {filas.map(({ grupo, punto }) => {
          // Mismo criterio de decimales que `CajaFormula`/`FormulaInstanciada`:
          // entre 2 y 3, según los decimales del propio umbral.
          const decimales = decimalesDe(punto.threshold_low ?? punto.threshold_high);
          const f = (v: number | null) => (regresion ? formato(metrica, v) : formatoNumero(v, decimales));
          return (
            <TableRow key={grupo}>
              <TableCell>{etiquetaGrupo(grupo, groupContext)}</TableCell>
              <TableCell className="tabular-nums">{f(punto.value)}</TableCell>
              <TableCell className="tabular-nums">
                {punto.interval_low !== null && punto.interval_high !== null
                  ? `${f(punto.interval_low)} – ${f(punto.interval_high)}`
                  : "—"}
              </TableCell>
              <TableCell className="tabular-nums">
                {punto.threshold_low === null && punto.threshold_high === null
                  ? "—"
                  : [
                      punto.threshold_low !== null ? `≥ ${f(punto.threshold_low)}` : null,
                      punto.threshold_high !== null ? `≤ ${f(punto.threshold_high)}` : null,
                    ]
                      .filter((v): v is string => v !== null)
                      .join(" / ")}
              </TableCell>
              <TableCell>
                <StateBadge estado={punto.state} size="sm" />
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
