/**
 * Diferencias de error entre grupos de una regresión: valor,
 * umbral, estado y lectura en palabras de cada medida de diferencia. Desde
 * `md` es una tabla; en móvil cada medida es una tarjeta, porque con la tabla
 * en scroll horizontal la lectura en palabras quedaba fuera de la vista.
 */

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StateBadge } from "@/components/vigia";
import type { Measurement } from "@/api/types";

import { fraseDiferenciaError } from "./regresion-equidad-datos";

export interface TablaDiferenciasErrorProps {
  medidas: Measurement[];
  etiqueta: (clave: string) => string;
  formato: (clave: string, valor: number) => string;
}

function textoUmbral(m: Measurement, formato: TablaDiferenciasErrorProps["formato"]): string {
  if (m.threshold_low === null && m.threshold_high === null) return "—";
  return [
    m.threshold_low !== null ? `≥ ${formato(m.metric_key, m.threshold_low)}` : null,
    m.threshold_high !== null ? `≤ ${formato(m.metric_key, m.threshold_high)}` : null,
  ]
    .filter((v): v is string => v !== null)
    .join(" / ");
}

function valorTexto(m: Measurement, formato: TablaDiferenciasErrorProps["formato"]): string {
  return m.value === null ? "n/d" : formato(m.metric_key, m.value);
}

function enPalabras(m: Measurement, formato: TablaDiferenciasErrorProps["formato"]): string {
  return m.value === null ? (m.motivo ?? "Sin valor.") : fraseDiferenciaError(m.metric_key, m.value, formato);
}

export function TablaDiferenciasError({ medidas, etiqueta, formato }: TablaDiferenciasErrorProps) {
  return (
    <div className="flex flex-col gap-2" data-testid="tabla-diferencias-error">
      <h4 className="text-sm font-semibold">Diferencias de error entre grupos</h4>
      <div className="hidden md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Medida</TableHead>
              <TableHead className="text-right">Valor</TableHead>
              <TableHead>Umbral</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>En palabras</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {medidas.map((m) => (
              <TableRow key={m.metric_key}>
                <TableCell>{etiqueta(m.metric_key)}</TableCell>
                <TableCell className="text-right tabular-nums">{valorTexto(m, formato)}</TableCell>
                <TableCell className="tabular-nums">{textoUmbral(m, formato)}</TableCell>
                <TableCell>
                  <StateBadge estado={m.state} size="sm" />
                </TableCell>
                <TableCell className="whitespace-normal text-muted-foreground">{enPalabras(m, formato)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <ul className="flex flex-col gap-2 md:hidden" data-testid="diferencias-error-tarjetas">
        {medidas.map((m) => (
          <li key={m.metric_key} className="flex flex-col gap-1 rounded-lg border border-border p-3 text-sm">
            <div className="flex items-start justify-between gap-2">
              <span className="font-semibold">{etiqueta(m.metric_key)}</span>
              <StateBadge estado={m.state} size="sm" />
            </div>
            <span className="tabular-nums">
              {valorTexto(m, formato)} · umbral {textoUmbral(m, formato)}
            </span>
            <span className="text-muted-foreground">{enPalabras(m, formato)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
