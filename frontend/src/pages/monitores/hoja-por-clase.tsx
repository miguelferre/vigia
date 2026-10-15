/**
 * Hoja «Medidas por clase» de la tarjeta ampliada: el valor de
 * la métrica en cada clase, del último lote. Son medidas informativas: no
 * tienen umbral, así que aquí nunca hay un estado «Correcto» ni «Alerta»,
 * solo el valor o, si no se pudo calcular, «sin datos» con su motivo (clase
 * rara en la ventana, o sin positivos y negativos de esa clase).
 */

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useTipoTarea } from "@/hooks/useTipoTarea";
import { claseDeGrupo } from "@/lib/tipo-tarea";
import { formatoNumero } from "@/lib/metrics";

import { ultimosPorGrupo, type SerieAgrupada } from "./tipos";
import { useEvaluationDetail } from "./usarEvaluacion";

export interface HojaPorClaseProps {
  metrica: string;
  /** Series por clase de esta métrica (`group_code = "clase:<clave>"`). */
  series: SerieAgrupada[];
}

export function HojaPorClase({ metrica, series }: HojaPorClaseProps) {
  const { clases } = useTipoTarea();
  const filas = ultimosPorGrupo(series).map(({ grupo, punto }) => ({
    grupo,
    clase: claseDeGrupo(grupo) ?? grupo,
    punto,
  }));
  // Orden de las clases del proyecto; las que el proyecto no declare, al final por nombre.
  filas.sort((a, b) => {
    const ia = clases.indexOf(a.clase);
    const ib = clases.indexOf(b.clase);
    if (ia === -1 && ib === -1) return a.clase.localeCompare(b.clase);
    return (ia === -1 ? Number.MAX_SAFE_INTEGER : ia) - (ib === -1 ? Number.MAX_SAFE_INTEGER : ib);
  });
  // El motivo de un «sin datos» no viaja en `/timeline`: se lee del detalle de la evaluación del último punto.
  const sinDatos = filas.find((f) => f.punto.state === "sin_datos");
  const detalleQ = useEvaluationDetail(sinDatos?.punto.evaluation_id ?? null);
  const motivoDe = (grupo: string): string | null =>
    detalleQ.data?.measurements.find((m) => m.metric_key === metrica && m.group_code === grupo)?.motivo ?? null;

  if (filas.length === 0) return null;

  return (
    <div className="flex flex-col gap-2" data-testid="medidas-por-clase">
      <p className="text-xs text-muted-foreground">
        Cada clase contra el resto, en el último lote. Son medidas informativas: no tienen umbral y no abren alertas.
      </p>
      <div className="max-h-72 overflow-auto rounded-lg border">
        <Table>
          <TableHeader className="sticky top-0 bg-card">
            <TableRow>
              <TableHead>Clase</TableHead>
              <TableHead className="text-right">Valor</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.map(({ grupo, clase, punto }) => {
              const motivo = punto.value === null ? motivoDe(grupo) : null;
              return (
                <TableRow key={grupo}>
                  <TableCell className="max-w-72 whitespace-normal [overflow-wrap:anywhere]">{clase}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {punto.value === null ? (
                      <span className="flex flex-col items-end gap-0.5">
                        <span className="text-muted-foreground">sin datos</span>
                        {motivo ? (
                          <span className="max-w-64 whitespace-normal text-xs text-muted-foreground">{motivo}</span>
                        ) : null}
                      </span>
                    ) : (
                      formatoNumero(punto.value)
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

export default HojaPorClase;
