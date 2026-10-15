/**
 * Violín partido de la predicción por grupo: la distribución del
 * valor que predice el modelo en el grupo de referencia (mitad izquierda,
 * `--chart-3`) y en el supervisado (mitad derecha, `--chart-2`), con la
 * mediana de cada uno. Sale de `details.prediccion_por_grupo` (histograma con
 * los mismos cortes en los dos grupos). Mismo dibujo que `ViolinPartido`, con
 * el eje en la unidad de la salida en lugar de 0 a 1.
 */

import { formatoCorto, formatoMetrica, formatoNumero } from "@/lib/metrics";

import { fraseDiferenciaMedianas } from "./regresion-equidad-datos";
import { densidadPorTramo, siluetaMonotona } from "./violin-silueta";
import { ticksRedondos } from "./regresion-datos";
import type { GrupoRegresion, PrediccionGrupo } from "./regresion-equidad-datos";

const ANCHO = 420;
const ALTO = 220;
const ARRIBA = 10;
const ABAJO = 34;
const HUECO = 10;

interface Props {
  grupos: PrediccionGrupo[];
  nombres: Record<GrupoRegresion, string>;
  unidad: string | null;
}

function camino(cx: number, puntos: { x: number; y: number }[], signo: 1 | -1): string {
  if (puntos.length === 0) return "";
  const lado = puntos.map((p) => `L${(cx + signo * p.x).toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  return `M${cx.toFixed(1)},${puntos[0]!.y.toFixed(1)} ${lado} L${cx.toFixed(1)},${puntos[puntos.length - 1]!.y.toFixed(1)} Z`;
}

export function ViolinPrediccionGrupos({ grupos, nombres, unidad }: Props) {
  const sup = grupos.find((g) => g.grupo === "unpriv");
  const ref = grupos.find((g) => g.grupo === "priv");
  const edges = (sup?.histograma ?? ref?.histograma)?.binEdges;
  if (!edges || edges.length < 3) return null;
  const min = edges[0]!;
  const max = edges[edges.length - 1]!;
  const ticks = ticksRedondos(min, max);
  const y0 = ALTO - ABAJO;
  const yDe = (v: number) => y0 - ((v - min) / (max - min)) * (y0 - ARRIBA);
  const cx = ANCHO / 2;
  const medio = ANCHO / 2 - HUECO;

  const silueta = (g: PrediccionGrupo | undefined) =>
    g?.histograma && g.n > 0 ? siluetaMonotona(g.histograma.binEdges, densidadPorTramo(g.histograma.binEdges, g.histograma.counts)) : [];
  const sSup = silueta(sup);
  const sRef = silueta(ref);
  const densMax = Math.max(0, ...sSup.map((p) => p.densidad), ...sRef.map((p) => p.densidad));
  const escala = densMax > 0 ? (medio * 0.85) / densMax : 0;
  const puntos = (s: { valor: number; densidad: number }[]) => s.map((p) => ({ x: p.densidad * escala, y: yDe(p.valor) }));
  const densEn = (s: { valor: number; densidad: number }[], v: number) => {
    let mejor = 0;
    let dist = Infinity;
    for (const p of s) {
      const d = Math.abs(p.valor - v);
      if (d < dist) {
        dist = d;
        mejor = p.densidad;
      }
    }
    return mejor;
  };
  const mediana = (g: PrediccionGrupo | undefined, s: { valor: number; densidad: number }[], signo: 1 | -1) =>
    g?.cuantiles && s.length > 0 ? { x: cx + signo * densEn(s, g.cuantiles.p50) * escala, y: yDe(g.cuantiles.p50) } : null;
  const pSup = mediana(sup, sSup, 1);
  const pRef = mediana(ref, sRef, -1);
  const frase = fraseDiferenciaMedianas(sup?.cuantiles?.p50 ?? null, ref?.cuantiles?.p50 ?? null, (v) =>
    formatoMetrica("mean_absolute_error", v, unidad),
  );

  return (
    <div className="flex flex-col gap-2" data-testid="violin-prediccion-grupos">
      <svg width={ANCHO} height={ALTO} viewBox={`0 0 ${ANCHO} ${ALTO}`} className="max-w-full" role="img" aria-label="Distribución de la predicción por grupo">
        {ticks.map((v) => (
          <line key={`t-${v}`} x1={0} y1={yDe(v)} x2={ANCHO} y2={yDe(v)} stroke="var(--line)" />
        ))}
        <line x1={0} y1={y0} x2={ANCHO} y2={y0} stroke="var(--border)" />
        <line x1={cx} y1={ARRIBA} x2={cx} y2={y0} stroke="var(--border)" />
        {sSup.length > 0 ? <path d={camino(cx, puntos(sSup), 1)} fill="var(--chart-2)" fillOpacity={0.45} stroke="var(--chart-2)" strokeWidth={1.5} /> : null}
        {sRef.length > 0 ? <path d={camino(cx, puntos(sRef), -1)} fill="var(--chart-3)" fillOpacity={0.45} stroke="var(--chart-3)" strokeWidth={1.5} /> : null}
        {pSup ? <circle cx={pSup.x} cy={pSup.y} r={3} fill="var(--card)" stroke="var(--chart-2)" strokeWidth={2} /> : null}
        {pRef ? <circle cx={pRef.x} cy={pRef.y} r={3} fill="var(--card)" stroke="var(--chart-3)" strokeWidth={2} /> : null}
        <text x={cx - medio / 2} y={ALTO - 8} fontSize={11} fontWeight={600} fill="var(--foreground)" textAnchor="middle">
          {nombres.priv.length > 34 ? `${nombres.priv.slice(0, 33)}…` : nombres.priv}
        </text>
        <text x={cx + medio / 2} y={ALTO - 8} fontSize={11} fontWeight={600} fill="var(--foreground)" textAnchor="middle">
          {nombres.unpriv.length > 34 ? `${nombres.unpriv.slice(0, 33)}…` : nombres.unpriv}
        </text>
        <text x={cx - medio / 2} y={ALTO - 20} fontSize={10} fill="var(--muted-foreground)" textAnchor="middle">
          {ref ? `n ${formatoNumero(ref.n, 0)}` : "n/d"}
        </text>
        <text x={cx + medio / 2} y={ALTO - 20} fontSize={10} fill="var(--muted-foreground)" textAnchor="middle">
          {sup ? `n ${formatoNumero(sup.n, 0)}` : "n/d"}
        </text>
        {ticks.map((v) => (
          <text key={`e-${v}`} x={4} y={yDe(v) - 3} fontSize={9} fill="var(--muted-foreground)">
            {formatoCorto(v, 2)}
          </text>
        ))}
        {unidad ? (
          <text x={4} y={9} fontSize={9} fontWeight={600} fill="var(--muted-foreground)">
            {unidad}
          </text>
        ) : null}
      </svg>
      {frase ? <p className="text-xs text-muted-foreground">{frase}</p> : null}
    </div>
  );
}
