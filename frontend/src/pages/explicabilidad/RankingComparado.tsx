/**
 * «Línea base frente a ahora»: barra violeta (`--chart-1`)
 * con la importancia actual, punto teal (`--chart-3`, anillo de superficie)
 * con la de la línea base, visible dentro y fuera de la barra. El punto era
 * gris (`--muted-foreground`); pasa a teal (teal línea
 * base, violeta lote), por token en los cuatro temas.
 * SVG propio con ancho real por `useAnchoContenedor` (patrón
 * `violin-svg.tsx`: tooltip por fila con hover y foco); ticks de
 * `violin-silueta.ts` (matemática de dominio genérica, no atada al violín).
 */

import { useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useAnchoContenedor } from "@/hooks/useAnchoContenedor";
import { formatoCorto } from "@/lib/metrics";
import { dominioYTicks } from "@/pages/monitores/violin-silueta";
import type { FilaComparada } from "./ranking-comparado-datos";
import {
  anchoEtiquetas,
  decimalesImportancia,
  lineasTooltip,
  pathBarra,
  textoEtiqueta,
} from "./ranking-comparado-utiles";

export interface RankingComparadoProps {
  filas: FilaComparada[];
  onClickFila: (featureTecnico: string) => void;
  /** Formato de la importancia en el tooltip y el lector de pantalla; en regresión lleva la unidad. */
  formato?: (valor: number) => string;
  /** Título del eje; en regresión dice qué mide la barra y la unidad. */
  tituloEje?: string;
}

const ROW_H = 30;
const ARRIBA = 10;
const ABAJO = 34;
const DER = 16;

export function RankingComparado({ filas, onClickFila, formato, tituloEje = "Importancia" }: RankingComparadoProps) {
  const [ref, ancho] = useAnchoContenedor<HTMLDivElement>();
  const [activo, setActivo] = useState<number | null>(null);

  if (filas.length === 0) return null;

  const izq = anchoEtiquetas(filas);
  const alto = filas.length * ROW_H + ARRIBA + ABAJO;
  const maxVal = Math.max(0, ...filas.flatMap((f) => [f.base ?? 0, f.actual ?? 0]));
  const dominioMax = maxVal > 0 ? maxVal * 1.12 : 1;
  const decimales = decimalesImportancia(dominioMax);
  const { ticks } = dominioYTicks(0, dominioMax);
  const x1 = Math.max(izq + 40, ancho - DER);
  const xDe = (v: number) => izq + (x1 - izq) * Math.min(1, v / dominioMax);
  const yEje = alto - ABAJO;

  const posicionTooltip = (i: number) => {
    const f = filas[i];
    const xs = [f.base, f.actual].filter((v): v is number => v !== null).map(xDe);
    const xMax = xs.length > 0 ? Math.max(...xs) : (izq + x1) / 2;
    const aDerecha = xMax + 12 + 210 <= ancho;
    return aDerecha ? { left: xMax + 12, transform: undefined } : { left: xMax - 12, transform: "translateX(-100%)" };
  };

  return (
    <div className="flex flex-col gap-2">
      <div ref={ref} style={{ minHeight: alto }}>
        {ancho === 0 ? (
          <Skeleton className="w-full" style={{ height: alto }} />
        ) : (
          <div className="relative">
            <svg
              width={ancho}
              height={alto}
              viewBox={`0 0 ${ancho} ${alto}`}
              aria-label="Línea base frente a ahora, importancia por variable"
            >
              {ticks.map((v) => (
                <g key={v}>
                  <line x1={xDe(v)} y1={ARRIBA - 4} x2={xDe(v)} y2={yEje} stroke="var(--line)" />
                  <text x={xDe(v)} y={yEje + 14} fontSize={10} fill="var(--muted-foreground)" textAnchor="middle">
                    {formatoCorto(v, decimales)}
                  </text>
                </g>
              ))}
              <text x={(izq + x1) / 2} y={alto - 4} fontSize={10} fill="var(--muted-foreground)" textAnchor="middle">
                {tituloEje}
              </text>
              <line x1={izq} y1={yEje} x2={x1} y2={yEje} stroke="var(--border)" />

              {filas.map((f, i) => {
                const y = ARRIBA + i * ROW_H + ROW_H / 2;
                const xBase = f.base !== null ? xDe(f.base) : null;
                const xActual = f.actual !== null ? xDe(f.actual) : null;
                // featureTecnico a secas no basta: puede repetirse entre top
                // y salidas si el resumen queda un instante viejo.
                return (
                  <g
                    key={`${f.featureTecnico}-${i}`}
                    role="button"
                    tabIndex={0}
                    aria-label={lineasTooltip(f, formato).join(". ")}
                    style={{ cursor: "pointer" }}
                    onMouseEnter={() => setActivo(i)}
                    onMouseLeave={() => setActivo(null)}
                    onFocus={() => setActivo(i)}
                    onBlur={() => setActivo(null)}
                    onClick={() => onClickFila(f.featureTecnico)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onClickFila(f.featureTecnico);
                      }
                    }}
                  >
                    <rect
                      x={0}
                      y={y - ROW_H / 2}
                      width={ancho}
                      height={ROW_H}
                      fill={activo === i ? "var(--muted)" : "transparent"}
                    />
                    <text
                      x={izq - 10}
                      y={y + 4}
                      fontSize={11}
                      textAnchor="end"
                      fill={f.marcada || f.base === null ? "var(--muted-foreground)" : "var(--foreground)"}
                    >
                      {textoEtiqueta(f)}
                    </text>
                    {xActual !== null ? <path d={pathBarra(izq, xActual, y)} fill="var(--chart-1)" /> : null}
                    {xBase !== null ? (
                      <circle cx={xBase} cy={y} r={5} fill="var(--chart-3)" stroke="var(--card)" strokeWidth={2} />
                    ) : null}
                  </g>
                );
              })}
            </svg>

            {activo !== null && filas[activo] ? (
              <div
                className="pointer-events-none absolute z-10 flex min-w-44 flex-col gap-1 rounded-md p-2.5 text-xs"
                style={{
                  left: posicionTooltip(activo).left,
                  top: Math.min(ARRIBA + activo * ROW_H, Math.max(0, alto - 92)),
                  transform: posicionTooltip(activo).transform,
                  background: "var(--card)",
                  color: "var(--card-foreground)",
                  boxShadow: "var(--elevation-pop)",
                }}
              >
                {lineasTooltip(filas[activo], formato).map((linea, i) => (
                  <p key={i} className={i === 0 ? "font-semibold" : undefined}>
                    {linea}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3.5 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-2 w-4 rounded-[2px]" style={{ background: "var(--chart-1)" }} />
          Ahora (barra)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block size-2.5 rounded-full"
            style={{ background: "var(--chart-3)", boxShadow: "0 0 0 2px var(--card)" }}
          />
          Línea base (punto)
        </span>
      </div>
    </div>
  );
}

export default RankingComparado;
