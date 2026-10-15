/**
 * Historial de ensayos del laboratorio: cada fila es un
 * `ResultadoLab` ya resuelto, con el estado del monitor clave de su fase y
 * el valor de la medida clave, junto a su umbral. Más reciente primero, sin
 * plegar nada: el efecto se ve mirando la tabla, que es el criterio de
 * cierre ("en dos movimientos"). Los parámetros se nombran con la etiqueta
 * del contenido, ninguna clave en crudo en pantalla, y se formatean
 * con los decimales que su `paso` implica (450, 0,33, 1,0).
 */

import { useEvaluations } from "@/api/queries";
import type { ParametroLaboratorio } from "@/api/queries-contenido";
import type { EstadoMotor, Measurement, MonitorType } from "@/api/types";
import { EmptyState, MetricLabel, StateBadge } from "@/components/vigia";
import { formatoNumero } from "@/lib/metrics";
import { medida } from "@/components/vigia/calculo-datos";
import { useEvaluationDetail } from "@/pages/monitores/usarEvaluacion";

import { METRICA_CLAVE_POR_MONITOR, monitorClave, type ResultadoLab } from "./laboratorio-parametros";

export interface ResultadoLaboratorioProps {
  projectId: number;
  resultados: ResultadoLab[];
  /** `laboratorio.parametros` del contenido: etiqueta en español y paso de cada clave. */
  parametros: readonly ParametroLaboratorio[];
}

function formatoHora(ts: number): string {
  return new Date(ts).toLocaleTimeString("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Decimales de un número por su representación (1 → 0, 0,1 → 1, 0,05 → 2), con tope. */
function decimalesDe(n: number, tope = 2): number {
  const texto = String(n);
  const coma = texto.indexOf(".");
  return coma < 0 ? 0 : Math.min(tope, texto.length - coma - 1);
}

/**
 * Los decimales del paso del parámetro, y al menos los que el valor trae
 * (la edad media por defecto es 62,4 con paso 1: se enseña 62,4, no 62).
 */
function formatoValor(v: number, definicion: ParametroLaboratorio | undefined): string {
  const porPaso = definicion ? decimalesDe(definicion.paso) : 2;
  return formatoNumero(v, Math.max(porPaso, decimalesDe(v)));
}

function formatoParams(params: Record<string, unknown>, parametros: readonly ParametroLaboratorio[]): string {
  const entradas = Object.entries(params).filter(([k]) => k !== "seed");
  if (entradas.length === 0) return "valores por defecto";
  return entradas
    .map(([k, v]) => {
      const definicion = parametros.find((p) => p.clave === k);
      const valor = typeof v === "number" ? formatoValor(v, definicion) : String(v);
      return `${definicion?.etiqueta ?? k}: ${valor}`;
    })
    .join(" · ");
}

function CeldaMedida({ measurement }: { measurement: Measurement | undefined }) {
  if (!measurement) return <span className="text-muted-foreground">sin medida</span>;
  const umbral = measurement.threshold_low ?? measurement.threshold_high;
  return (
    <span>
      {formatoNumero(measurement.value)}
      {umbral !== null && umbral !== undefined ? (
        <span className="text-muted-foreground"> · umbral {formatoNumero(umbral)}</span>
      ) : null}
    </span>
  );
}

interface FilaResultadoProps {
  projectId: number;
  resultado: ResultadoLab;
  parametros: readonly ParametroLaboratorio[];
}

function FilaResultado({ projectId, resultado, parametros }: FilaResultadoProps) {
  const monitor: MonitorType = monitorClave(resultado.expected);
  const metricKey = METRICA_CLAVE_POR_MONITOR[monitor];
  const evaluacionesQ = useEvaluations(projectId, {
    monitor_type: monitor,
    batch_id: resultado.batchId,
    limit: 1,
  });
  const evaluationId = evaluacionesQ.data?.items[0]?.id ?? null;
  const detalleQ = useEvaluationDetail(evaluationId);
  const estado: EstadoMotor | null =
    (resultado.states[monitor] as EstadoMotor | undefined) ?? detalleQ.data?.worst_state ?? null;
  const m = detalleQ.data ? medida(detalleQ.data, metricKey) : undefined;

  return (
    <tr className="border-b last:border-0">
      <td className="p-3 align-middle whitespace-nowrap">{formatoHora(resultado.ts)}</td>
      <td className="p-3 align-middle">{resultado.faseTitulo}</td>
      <td className="p-3 align-middle">{formatoParams(resultado.params, parametros)}</td>
      <td className="p-3 align-middle">
        <MetricLabel metrica={metricKey} />
      </td>
      <td className="p-3 align-middle">
        <StateBadge estado={estado} size="sm" />
      </td>
      <td className="p-3 align-middle">
        <CeldaMedida measurement={m} />
      </td>
    </tr>
  );
}

export function ResultadoLaboratorio({ projectId, resultados, parametros }: ResultadoLaboratorioProps) {
  if (resultados.length === 0) {
    return (
      <EmptyState
        titulo="Sin ensayos todavía"
        descripcion="Elige una fase, mueve un parámetro y ejecuta: el resultado aparece aquí, sin avanzar el caso."
      />
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full caption-bottom text-sm">
        <thead className="[&_tr]:border-b">
          <tr className="border-b">
            <th className="h-9 px-3 text-left align-middle text-muted-foreground">Hora</th>
            <th className="h-9 px-3 text-left align-middle text-muted-foreground">Fase</th>
            <th className="h-9 px-3 text-left align-middle text-muted-foreground">
              Parámetros
            </th>
            <th className="h-9 px-3 text-left align-middle text-muted-foreground">
              Métrica clave
            </th>
            <th className="h-9 px-3 text-left align-middle text-muted-foreground">Estado</th>
            <th className="h-9 px-3 text-left align-middle text-muted-foreground">Valor</th>
          </tr>
        </thead>
        <tbody>
          {resultados.map((r) => (
            <FilaResultado key={r.ts} projectId={projectId} resultado={r} parametros={parametros} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
