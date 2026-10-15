/**
 * Distintivo de estado del motor.
 *
 * Mapea `ok | aviso | alerta | inestable | sin_datos` a los tokens
 * `--state-*` de `themes/tokens.css`. Ningún color literal.
 *
 * `aviso` y `alerta` se pintan rellenas (fondo del color de estado,
 * texto `--state-on-fill`); `ok`, `inestable` y `sin_datos` siguen con borde
 * y texto `--foreground`, como antes. El
 * punto de color se sustituye por el glifo del estado (`lib/iconos.ts`) y
 * el fondo de `aviso` se queda en `--state-warn` (uso "texto": aquí hay
 * texto encima, y es donde ese token cumple contraste), no en
 * `--state-warn-fill`.
 */

import { cn } from "@/lib/utils";
import { ETIQUETA_ESTADO, TOKEN_ESTADO, TOKEN_ESTADO_RELLENO } from "@/lib/metrics";
import { GLIFO_ESTADO } from "@/lib/iconos";
import type { EstadoMotor } from "@/api/types";

export interface StateBadgeProps {
  estado: EstadoMotor | null | undefined;
  /** Texto alternativo a la etiqueta por defecto del estado. */
  texto?: string;
  size?: "sm" | "md";
  className?: string;
}

/**
 * Color del estado listo para `style`. `uso: "texto"` (por defecto) da el
 * token que cumple contraste de texto y de chip con texto; `uso: "relleno"`
 * da el token pensado para superficies sin texto encima (luces, líneas
 * superiores, series de gráfica, sparklines) — solo difiere en `aviso`.
 */
export function colorEstado(
  estado: EstadoMotor | null | undefined,
  uso: "texto" | "relleno" = "texto",
): string {
  const valor = estado ?? "sin_datos";
  const token = uso === "relleno" ? TOKEN_ESTADO_RELLENO[valor] : TOKEN_ESTADO[valor];
  return `var(${token})`;
}

/** Estados que se pintan como insignia rellena en vez de con borde. */
const ESTADOS_RELLENOS: ReadonlySet<EstadoMotor> = new Set(["aviso", "alerta"]);

export function StateBadge({ estado, texto, size = "md", className }: StateBadgeProps) {
  const valor: EstadoMotor = estado ?? "sin_datos";
  const color = colorEstado(valor);
  const relleno = ESTADOS_RELLENOS.has(valor);
  const estilo = relleno
    ? { background: color, borderColor: color, color: "var(--state-on-fill)" }
    : { borderColor: color, color: "var(--foreground)" };
  const Glifo = GLIFO_ESTADO[valor];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border font-semibold whitespace-nowrap",
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
        className,
      )}
      style={estilo}
      title={ETIQUETA_ESTADO[valor]}
    >
      <Glifo
        className={size === "sm" ? "size-3" : "size-3.5"}
        strokeWidth={1.75}
        // Sin relleno (ok, inestable, sin datos) el glifo lleva el color del
        // estado, como llevaba el punto: el color acompaña al glifo.
        style={{ color: relleno ? "var(--state-on-fill)" : color }}
        aria-hidden="true"
      />
      {texto ?? ETIQUETA_ESTADO[valor]}
    </span>
  );
}
