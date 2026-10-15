/**
 * Barras de error por grupo de una regresión: dos tarjetas, una
 * con el error absoluto medio (barras desde 0) y otra con el sesgo medio
 * (barras divergentes desde un eje central: a la izquierda el modelo se queda
 * corto, a la derecha se pasa). Cada barra lleva su `n`. Barras de HTML y no
 * de Recharts: los nombres de grupo son largos y el sesgo es con signo, y así
 * el valor y las palabras van junto a la barra sin etiquetas flotantes.
 */

import { Card } from "@/components/ui/card";
import { formatoMetrica, formatoNumero } from "@/lib/metrics";

import { fraseSesgo } from "./regresion-datos";
import type { ErrorGrupo, GrupoRegresion } from "./regresion-equidad-datos";

const COLOR: Record<GrupoRegresion, string> = { unpriv: "var(--chart-2)", priv: "var(--chart-3)" };

interface Props {
  filas: ErrorGrupo[];
  nombres: Record<GrupoRegresion, string>;
  unidad: string | null;
}

function Fila({ nombre, n, children, texto }: { nombre: string; n: number; children: React.ReactNode; texto: string }) {
  return (
    <li className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="min-w-0 [overflow-wrap:anywhere]">
          {nombre} <span className="text-xs text-muted-foreground">n = {formatoNumero(n, 0)}</span>
        </span>
        <b className="shrink-0 font-semibold tabular-nums">{texto}</b>
      </div>
      {children}
    </li>
  );
}

export function BarrasErrorPorGrupo({ filas, nombres, unidad }: Props) {
  const conMae = filas.filter((f) => f.mae !== null);
  const maxMae = Math.max(0, ...conMae.map((f) => f.mae as number));
  const conSesgo = filas.filter((f) => f.sesgo !== null);
  const maxSesgo = Math.max(0, ...conSesgo.map((f) => Math.abs(f.sesgo as number)));
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2" data-testid="barras-error-por-grupo">
      <Card className="flex flex-col gap-3 px-4 py-3.5">
        <div className="flex flex-col gap-0.5">
          <h4 className="text-[13px] font-semibold">Error absoluto medio por grupo</h4>
          <span className="text-xs text-muted-foreground">
            Cuánto se aleja la predicción del valor real, de media{unidad ? `, en ${unidad}` : ""}. Más corta es mejor.
          </span>
        </div>
        <ul className="flex flex-col gap-3">
          {filas.map((f) => (
            <Fila key={f.grupo} nombre={nombres[f.grupo]} n={f.n} texto={formatoMetrica("mean_absolute_error", f.mae, unidad)}>
              {f.mae === null ? (
                <span className="text-xs text-muted-foreground">{f.motivo ?? "Sin datos suficientes en este grupo."}</span>
              ) : (
                <div className="h-2.5 w-full rounded-full bg-muted">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${maxMae > 0 ? Math.max(2, (f.mae / maxMae) * 100) : 0}%`, background: COLOR[f.grupo] }}
                  />
                </div>
              )}
            </Fila>
          ))}
        </ul>
      </Card>
      <Card className="flex flex-col gap-3 px-4 py-3.5">
        <div className="flex flex-col gap-0.5">
          <h4 className="text-[13px] font-semibold">Sesgo medio por grupo</h4>
          <span className="text-xs text-muted-foreground">
            Predicción menos valor real, de media{unidad ? `, en ${unidad}` : ""}. Cerca del eje es mejor: a la izquierda
            el modelo se queda corto y a la derecha se pasa.
          </span>
        </div>
        <ul className="flex flex-col gap-3">
          {filas.map((f) => (
            <Fila key={f.grupo} nombre={nombres[f.grupo]} n={f.n} texto={formatoMetrica("mean_error", f.sesgo, unidad)}>
              {f.sesgo === null ? (
                <span className="text-xs text-muted-foreground">{f.motivo ?? "Sin datos suficientes en este grupo."}</span>
              ) : (
                <>
                  <div className="relative h-2.5 w-full rounded-full bg-muted">
                    <div className="absolute inset-y-0 left-1/2 w-px bg-foreground/60" aria-hidden="true" />
                    <div
                      className="absolute inset-y-0 rounded-full"
                      style={{
                        background: COLOR[f.grupo],
                        width: `${maxSesgo > 0 ? Math.max(1, (Math.abs(f.sesgo) / maxSesgo) * 50) : 0}%`,
                        [f.sesgo < 0 ? "right" : "left"]: "50%",
                      }}
                    />
                  </div>
                  <span className="text-xs text-muted-foreground">{fraseSesgo(f.sesgo, unidad, "el valor real")}</span>
                </>
              )}
            </Fila>
          ))}
        </ul>
      </Card>
    </div>
  );
}
