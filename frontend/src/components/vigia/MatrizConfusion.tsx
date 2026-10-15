/**
 * Matriz de confusión 2x2 de una evaluación de calidad, con el porcentaje por fila y por columna.
 *
 * Fuente: `evaluation.result.details.confusion` (`{tp, fp, fn, tn}`), que
 * puede venir con los cuatro valores a `null` cuando el motor no tiene datos
 * suficientes (`core/quality.py:175-178`). La matriz degrada mostrando "sin
 * datos" en vez de "null", y sin dividir por cero.
 */

import { InfoTooltip } from "./InfoTooltip";
import { leerMatrizK } from "./calidad-multiclase-datos";
import { MatrizConfusionK } from "./MatrizConfusionK";
import { Skeleton } from "@/components/ui/skeleton";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { EvaluationDetail } from "@/api/types";

export interface MatrizConfusionProps {
  evaluacion: EvaluationDetail;
  /** Celdas que participan en la fórmula de la métrica ampliada: se marcan con un anillo. */
  resaltar?: Array<"tp" | "fp" | "fn" | "tn">;
}

interface Confusion {
  tp: number | null;
  fp: number | null;
  fn: number | null;
  tn: number | null;
}

function leerConfusion(result: EvaluationDetail["result"]): Confusion | null {
  if (!result || typeof result !== "object") return null;
  const details = (result as Record<string, unknown>).details;
  if (!details || typeof details !== "object") return null;
  const confusion = (details as Record<string, unknown>).confusion;
  if (!confusion || typeof confusion !== "object") return null;
  const c = confusion as Record<string, unknown>;
  const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
  return { tp: num(c.tp), fp: num(c.fp), fn: num(c.fn), tn: num(c.tn) };
}

/** Porcentaje de `parte` sobre `total`, o `null` si no se puede calcular. */
function porcentaje(parte: number | null, total: number | null): number | null {
  if (parte === null || total === null || total === 0) return null;
  return (parte / total) * 100;
}

function formatoPorcentaje(v: number | null): string {
  if (v === null) return "n/d";
  return `${v.toLocaleString("es-ES", { maximumFractionDigits: 0 })} %`;
}

interface CasillaProps {
  valor: number | null;
  colorToken: "--state-ok" | "--state-alert";
  filaPct: number | null;
  colPct: number | null;
  titulo: string;
  queMide: string;
  resaltada?: boolean;
}

function Casilla({ valor, colorToken, filaPct, colPct, titulo, queMide, resaltada }: CasillaProps) {
  const color = `var(${colorToken})`;
  return (
    <TableCell
      className={cn("align-top", resaltada && "ring-2 ring-inset ring-ring")}
      style={{ backgroundColor: `color-mix(in srgb, ${color} 12%, transparent)` }}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-semibold tabular-nums" style={{ color }}>
          {valor === null ? "sin datos" : valor.toLocaleString("es-ES")}
        </span>
        <InfoTooltip titulo={titulo} queMide={queMide} />
      </div>
      {valor !== null ? (
        <p className="mt-1 text-xs text-muted-foreground">
          {formatoPorcentaje(filaPct)} de la fila · {formatoPorcentaje(colPct)} de la columna
        </p>
      ) : null}
    </TableCell>
  );
}

function MatrizConfusion2x2({ evaluacion, resaltar }: MatrizConfusionProps) {
  const confusion = leerConfusion(evaluacion.result);
  const esRes = (clave: "tp" | "fp" | "fn" | "tn") => resaltar?.includes(clave) ?? false;

  if (!confusion || (confusion.tp === null && confusion.fp === null && confusion.fn === null && confusion.tn === null)) {
    return (
      <p className="text-sm text-muted-foreground">
        Sin datos de matriz de confusión en esta evaluación: hace falta más histórico con etiqueta.
      </p>
    );
  }

  const { tp, fp, fn, tn } = confusion;
  const filaPos = (tp ?? 0) + (fp ?? 0);
  const filaNeg = (fn ?? 0) + (tn ?? 0);
  const colPos = (tp ?? 0) + (fn ?? 0);
  const colNeg = (fp ?? 0) + (tn ?? 0);
  const total = filaPos + filaNeg;
  const filaPosSinDatos = tp === null && fp === null;
  const filaNegSinDatos = fn === null && tn === null;
  const colPosSinDatos = tp === null && fn === null;
  const colNegSinDatos = fp === null && tn === null;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">
        Filas: lo que predice el modelo. Columnas: lo que dice la etiqueta real. El porcentaje de cada
        casilla es sobre su fila y sobre su columna.
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead />
            <TableHead className="text-center">Real: positivo</TableHead>
            <TableHead className="text-center">Real: negativo</TableHead>
            <TableHead className="text-center">
              <span className="inline-flex items-center gap-1">
                Total de la fila
                <InfoTooltip
                  titulo="Total de la fila"
                  queMide="Cuántas veces el modelo predijo esta clase, sin importar si acertó."
                />
              </span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableHead>Predicho: positivo</TableHead>
            <Casilla
              valor={tp}
              colorToken="--state-ok"
              filaPct={porcentaje(tp, filaPos)}
              colPct={porcentaje(tp, colPos)}
              titulo="Verdaderos positivos"
              queMide="El modelo predijo positivo y la etiqueta real también era positiva: acierto."
              resaltada={esRes("tp")}
            />
            <Casilla
              valor={fp}
              colorToken="--state-alert"
              filaPct={porcentaje(fp, filaPos)}
              colPct={porcentaje(fp, colNeg)}
              titulo="Falsos positivos"
              queMide="El modelo predijo positivo pero la etiqueta real era negativa: falsa alarma."
              resaltada={esRes("fp")}
            />
            <TableCell className="text-center tabular-nums">
              {filaPosSinDatos ? "sin datos" : filaPos.toLocaleString("es-ES")}
            </TableCell>
          </TableRow>
          <TableRow>
            <TableHead>Predicho: negativo</TableHead>
            <Casilla
              valor={fn}
              colorToken="--state-alert"
              filaPct={porcentaje(fn, filaNeg)}
              colPct={porcentaje(fn, colPos)}
              titulo="Falsos negativos"
              queMide="El modelo predijo negativo pero la etiqueta real era positiva: caso que se escapa."
              resaltada={esRes("fn")}
            />
            <Casilla
              valor={tn}
              colorToken="--state-ok"
              filaPct={porcentaje(tn, filaNeg)}
              colPct={porcentaje(tn, colNeg)}
              titulo="Verdaderos negativos"
              queMide="El modelo predijo negativo y la etiqueta real también era negativa: acierto."
              resaltada={esRes("tn")}
            />
            <TableCell className="text-center tabular-nums">
              {filaNegSinDatos ? "sin datos" : filaNeg.toLocaleString("es-ES")}
            </TableCell>
          </TableRow>
          <TableRow>
            <TableHead>
              <span className="inline-flex items-center gap-1">
                Total de la columna
                <InfoTooltip
                  titulo="Total de la columna"
                  queMide="Cuántos casos tenían de verdad esta etiqueta, sin importar qué predijo el modelo."
                />
              </span>
            </TableHead>
            <TableCell className="text-center tabular-nums">
              {colPosSinDatos ? "sin datos" : colPos.toLocaleString("es-ES")}
            </TableCell>
            <TableCell className="text-center tabular-nums">
              {colNegSinDatos ? "sin datos" : colNeg.toLocaleString("es-ES")}
            </TableCell>
            <TableCell className="text-center font-semibold tabular-nums">
              {filaPosSinDatos && filaNegSinDatos ? "sin datos" : total.toLocaleString("es-ES")}
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  );
}

/**
 * Matriz de confusión de una evaluación de calidad según el tipo de tarea
 * `2x2` binaria (la de siempre) o `k x k` multiclase. Con
 * el proyecto cargando no se dibuja ninguna: un multiclase no parpadea
 * de 2x2 a `k x k`.
 */
export function MatrizConfusion({ evaluacion, resaltar }: MatrizConfusionProps) {
  const { caps } = useTipoTarea(evaluacion.project_id);
  if (!caps) return <Skeleton className="h-40 w-full" />;
  if (caps.matriz === "kxk") {
    const matriz = leerMatrizK(evaluacion.result);
    return matriz ? (
      <MatrizConfusionK matriz={matriz} />
    ) : (
      <p className="text-sm text-muted-foreground">
        Sin datos de matriz de confusión en esta evaluación: hace falta más histórico con etiqueta.
      </p>
    );
  }
  if (caps.matriz === null) return null;
  return <MatrizConfusion2x2 evaluacion={evaluacion} resaltar={resaltar} />;
}

export default MatrizConfusion;
