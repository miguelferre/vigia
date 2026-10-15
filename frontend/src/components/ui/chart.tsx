/* ChartContainer minimo al estilo shadcn/ui: envuelve Recharts en un
 * contenedor responsive y expone las variables --color-<key> a partir de
 * un ChartConfig, para que las series lean colores de tema (var(--chart-1)
 * etc.) en vez de colores fijos. */
import * as React from "react";
import { ResponsiveContainer, Tooltip } from "recharts";
import { cn } from "@/lib/utils";

export type ChartConfig = Record<string, { label: string; color: string }>;

interface ChartContainerProps extends React.HTMLAttributes<HTMLDivElement> {
  config: ChartConfig;
  children: React.ReactElement;
}

export function ChartContainer({ config, className, children, ...props }: ChartContainerProps) {
  const style = Object.fromEntries(
    Object.entries(config).map(([key, value]) => [`--color-${key}`, value.color]),
  ) as React.CSSProperties;

  return (
    <div
      data-slot="chart"
      className={cn("aspect-video w-full text-xs", className)}
      style={style}
      {...props}
    >
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  );
}

/**
 * Tooltip opaco: el `Tooltip` por defecto de
 * recharts pinta `contentStyle` semitransparente sobre las barras. Reexporta
 * `Tooltip` como `ChartTooltip` para que las gráficas de `ChartContainer`
 * usen el mismo camino que el resto (`HistogramaBaseLote.tsx`), con
 * `ChartTooltipContent` como contenido opaco por defecto.
 */
export const ChartTooltip = Tooltip;

interface ChartTooltipPayloadItem {
  dataKey?: string | number;
  name?: string | number;
  value?: number | string;
  color?: string;
}

interface ChartTooltipContentProps {
  active?: boolean;
  label?: string | number;
  payload?: ChartTooltipPayloadItem[];
  config: ChartConfig;
  /** Formatea cada valor de la lista; por defecto lo deja tal cual. */
  formatter?: (valor: number | string | undefined) => React.ReactNode;
}

export function ChartTooltipContent({ active, label, payload, config, formatter }: ChartTooltipContentProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div
      className="flex min-w-40 flex-col gap-1 rounded-md p-2.5 text-xs"
      style={{ background: "var(--card)", color: "var(--card-foreground)", boxShadow: "var(--elevation-pop)" }}
    >
      {label !== undefined ? <p className="font-semibold">{label}</p> : null}
      {payload.map((item, i) => {
        const clave = String(item.dataKey ?? item.name ?? i);
        const entrada = config[clave];
        return (
          <p key={clave} className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="inline-block size-2.5 rounded-[2px]" style={{ background: item.color ?? "var(--muted-foreground)" }} />
            {entrada?.label ?? item.name ?? clave}: {formatter ? formatter(item.value) : item.value}
          </p>
        );
      })}
    </div>
  );
}
