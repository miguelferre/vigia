/**
 * Tabla de error por grupo de una regresión: n, error absoluto
 * medio y sesgo medio de cada grupo, en la unidad de la salida y con el sesgo
 * dicho con palabras. Sale de `details.error_por_grupo` de la evaluación
 * de equidad; el mismo dato lo dibujan en barras `BarrasErrorPorGrupo` en
 * Equidad. Sin tabla se dice por qué (grupo con pocos registros, motivo).
 */

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatoMetrica, formatoNumero } from "@/lib/metrics";

import { fraseSesgo } from "./regresion-datos";
import type { ErrorGrupo, GrupoRegresion } from "./regresion-equidad-datos";

export interface TablaErrorPorGrupoProps {
  filas: ErrorGrupo[];
  nombres: Record<GrupoRegresion, string>;
  unidad: string | null;
}

export function TablaErrorPorGrupo({ filas, nombres, unidad }: TablaErrorPorGrupoProps) {
  return (
    <div data-testid="tabla-error-por-grupo">
      <ul className="flex flex-col gap-2 md:hidden" data-testid="error-por-grupo-tarjetas">
        {filas.map((f) => (
          <li key={f.grupo} className="flex flex-col gap-1 rounded-lg border border-border p-3 text-sm">
            <span className="font-semibold">{nombres[f.grupo]}</span>
            <span className="tabular-nums text-muted-foreground">{formatoNumero(f.n, 0)} registros con valor real</span>
            {f.mae === null && f.sesgo === null ? (
              <span className="text-muted-foreground">{f.motivo ?? "Sin datos suficientes en este grupo."}</span>
            ) : (
              <>
                <span className="tabular-nums">
                  Error absoluto medio {formatoMetrica("mean_absolute_error", f.mae, unidad)} · sesgo medio{" "}
                  {formatoMetrica("mean_error", f.sesgo, unidad)}
                </span>
                <span className="text-muted-foreground">{fraseSesgo(f.sesgo, unidad, "el valor real")}</span>
              </>
            )}
          </li>
        ))}
      </ul>
      <Table className="hidden md:table">
        <TableHeader>
          <TableRow>
            <TableHead>Grupo</TableHead>
            <TableHead className="text-right">Registros con valor real</TableHead>
            <TableHead className="text-right">Error absoluto medio</TableHead>
            <TableHead className="text-right">Sesgo medio</TableHead>
            <TableHead>Qué dice el sesgo</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filas.map((f) => (
            <TableRow key={f.grupo}>
              <TableCell>{nombres[f.grupo]}</TableCell>
              <TableCell className="text-right tabular-nums">{formatoNumero(f.n, 0)}</TableCell>
              {f.mae === null && f.sesgo === null ? (
                <TableCell colSpan={3} className="whitespace-normal text-muted-foreground">
                  {f.motivo ?? "Sin datos suficientes en este grupo."}
                </TableCell>
              ) : (
                <>
                  <TableCell className="text-right tabular-nums">{formatoMetrica("mean_absolute_error", f.mae, unidad)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatoMetrica("mean_error", f.sesgo, unidad)}</TableCell>
                  <TableCell className="whitespace-normal text-muted-foreground">{fraseSesgo(f.sesgo, unidad, "el valor real")}</TableCell>
                </>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
