/**
 * Tooltip del gráfico de barras de `detalle.tsx`.
 *
 * `contentStyle` con `var(--popover)` no existe como variable CSS (solo
 * `--color-popover` de Tailwind), así que el tooltip salía transparente.
 * Mismo patrón que `PuntoTooltip` en `pages/monitores/serie-partes.tsx`:
 * componente `content` propio con las clases de Tailwind que sí resuelven a
 * `--color-popover`.
 */

import { formatoNumero } from "@/lib/metrics";

interface Fila {
  feature: string;
  valor: number;
  rule: string | null;
}

export function TooltipBarra({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload?: unknown }[];
}) {
  if (!active || !payload || payload.length === 0) return null;
  const fila = payload[0]?.payload as Fila | undefined;
  if (!fila) return null;
  return (
    <div className="rounded-md border border-border bg-popover p-2 text-xs text-popover-foreground shadow-md">
      <p className="font-semibold">{fila.feature}</p>
      <p>{formatoNumero(fila.valor)}</p>
      {fila.rule ? <p className="text-muted-foreground">{fila.rule}</p> : null}
    </div>
  );
}

export default TooltipBarra;
