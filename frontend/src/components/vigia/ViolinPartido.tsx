/**
 * Violín partido de la probabilidad favorable: mitad izquierda con el grupo de referencia
 * (`priv`, `--chart-3`, el color de la línea base), mitad derecha con el
 * grupo supervisado (`unpriv`, `--chart-2`, el color de la equidad), con la mediana de cada mitad, el
 * umbral marcado y la frase calculada debajo. Vive dentro de `EscalaCociente` (`CalculoFormula.tsx`),
 * bajo la barra de escala del impacto dispar, no la sustituye.
 *
 * SVG propio (no `violin-svg.tsx`, que dibuja N violines completos por
 * lote): aquí es uno solo, partido por un eje central, sin scroll. Eje Y
 * fijo en 0 a 1 (la probabilidad), con `dominioYTicks`/`decimalesDelEje` de
 * `violin-silueta.ts` reutilizados tal cual (funciones puras, sin "lote").
 */

import { dominioYTicks, decimalesDelEje } from "@/pages/monitores/violin-silueta";
import { formatoNumero } from "@/lib/metrics";
import { formatoPorcentaje } from "./calculo-datos";
import {
  densidadEnValor,
  fraseCalculada,
  parseFavorableProbability,
  resolverGrupo,
  siluetaDeGrupo,
  type GrupoResuelto,
} from "./violin-partido-datos";

const ALTO = 190;
const ARRIBA = 10;
const ABAJO = 34;
const MEDIO_HUECO = 10;

/** Camino de una mitad: polígono entre el eje central (`cx`) y la silueta. */
function caminoMitad(cx: number, puntos: { x: number; y: number }[], signo: 1 | -1): string {
  if (puntos.length === 0) return "";
  const inicio = `M${cx.toFixed(1)},${puntos[0].y.toFixed(1)}`;
  const curva = puntos.map((p) => `L${(cx + signo * p.x).toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const cierre = `L${cx.toFixed(1)},${puntos[puntos.length - 1].y.toFixed(1)}`;
  return `${inicio} ${curva} ${cierre} Z`;
}

export interface ViolinPartidoProps {
  detalles: Record<string, unknown> | null;
  nombreSupervisado: string;
  nombreReferencia: string;
  ancho?: number;
  /** en multiclase, la probabilidad es la del conjunto de clases favorables (la suma); solo cambia el texto. */
  conjuntoFavorable?: boolean;
}

/** Devuelve `null` si `favorable_probability` falta o no cuadra: no se pinta nada, solo el motivo aparte. */
export function ViolinPartido({ detalles, nombreSupervisado, nombreReferencia, ancho = 420, conjuntoFavorable = false }: ViolinPartidoProps) {
  const { datos } = parseFavorableProbability(detalles);
  if (!datos) return null;

  const nBins = datos.bin_edges.length - 1;
  const supervisado = resolverGrupo(datos.by_group.unpriv, nBins);
  const referencia = resolverGrupo(datos.by_group.priv, nBins);
  if (!supervisado && !referencia) return null;

  const { ticks } = dominioYTicks(0, 1);
  const decimales = decimalesDelEje(0, 1);
  const y0 = ALTO - ABAJO;
  const y1 = ARRIBA;
  const yDe = (v: number) => y0 - v * (y0 - y1);
  const cx = ancho / 2;
  const medioAncho = ancho / 2 - MEDIO_HUECO;

  const siluetaSup = supervisado && !supervisado.motivo ? siluetaDeGrupo(datos.bin_edges, supervisado) : [];
  const siluetaRef = referencia && !referencia.motivo ? siluetaDeGrupo(datos.bin_edges, referencia) : [];
  const densidadMax = Math.max(0, ...siluetaSup.map((p) => p.densidad), ...siluetaRef.map((p) => p.densidad));
  const escala = densidadMax > 0 ? (medioAncho * 0.85) / densidadMax : 0;

  const puntosDe = (silueta: { valor: number; densidad: number }[]) =>
    silueta.map((p) => ({ x: p.densidad * escala, y: yDe(p.valor) }));

  const medianaPunto = (grupo: GrupoResuelto | null, silueta: { valor: number; densidad: number }[], signo: 1 | -1) => {
    if (!grupo || grupo.motivo || grupo.median === null) return null;
    const x = cx + signo * densidadEnValor(silueta, grupo.median) * escala;
    return { x, y: yDe(grupo.median) };
  };

  const puntoRef = medianaPunto(referencia, siluetaRef, -1);
  const puntoSup = medianaPunto(supervisado, siluetaSup, 1);

  const frase = fraseCalculada(
    datos.threshold,
    supervisado,
    referencia,
    nombreSupervisado,
    nombreReferencia,
    formatoNumero,
    formatoPorcentaje,
  );

  return (
    <div className="mt-3 flex flex-col gap-2">
      <svg width={ancho} height={ALTO} viewBox={`0 0 ${ancho} ${ALTO}`} aria-label={conjuntoFavorable ? "Violín de la probabilidad de las clases favorables por grupo" : "Violín de la probabilidad favorable por grupo"}>
        {ticks.map((v) => (
          <line key={`tick-${v}`} x1={0} y1={yDe(v)} x2={ancho} y2={yDe(v)} stroke="var(--line)" />
        ))}
        <line x1={0} y1={y0} x2={ancho} y2={y0} stroke="var(--border)" />
        <line x1={cx} y1={y1} x2={cx} y2={y0} stroke="var(--border)" />

        <line
          x1={0}
          y1={yDe(datos.threshold)}
          x2={ancho}
          y2={yDe(datos.threshold)}
          stroke="var(--foreground)"
          strokeOpacity={0.6}
          strokeDasharray="4 3"
        >
          <title>{datos.threshold_motivo ?? `Umbral: ${formatoNumero(datos.threshold, 2)}`}</title>
        </line>

        {siluetaSup.length > 0 ? (
          <path d={caminoMitad(cx, puntosDe(siluetaSup), 1)} fill="var(--chart-2)" fillOpacity={0.45} stroke="var(--chart-2)" strokeWidth={1.5} />
        ) : null}
        {siluetaRef.length > 0 ? (
          <path d={caminoMitad(cx, puntosDe(siluetaRef), -1)} fill="var(--chart-3)" fillOpacity={0.45} stroke="var(--chart-3)" strokeWidth={1.5} />
        ) : null}

        {puntoSup ? <circle cx={puntoSup.x} cy={puntoSup.y} r={3} fill="var(--card)" stroke="var(--chart-2)" strokeWidth={2} /> : null}
        {puntoRef ? <circle cx={puntoRef.x} cy={puntoRef.y} r={3} fill="var(--card)" stroke="var(--chart-3)" strokeWidth={2} /> : null}

        <text x={cx - medioAncho / 2} y={ALTO - 8} fontSize={11} fontWeight={600} fill="var(--foreground)" textAnchor="middle">
          {nombreReferencia}
        </text>
        <text x={cx + medioAncho / 2} y={ALTO - 8} fontSize={11} fontWeight={600} fill="var(--foreground)" textAnchor="middle">
          {nombreSupervisado}
        </text>
        <text x={cx - medioAncho / 2} y={ALTO - 20} fontSize={10} fill="var(--muted-foreground)" textAnchor="middle">
          {referencia?.motivo ?? (referencia ? `n ${formatoNumero(referencia.n, 0)}` : "n/d")}
        </text>
        <text x={cx + medioAncho / 2} y={ALTO - 20} fontSize={10} fill="var(--muted-foreground)" textAnchor="middle">
          {supervisado?.motivo ?? (supervisado ? `n ${formatoNumero(supervisado.n, 0)}` : "n/d")}
        </text>
        {ticks.map((v) => (
          <text key={`etq-${v}`} x={4} y={yDe(v) - 3} fontSize={9} fill="var(--muted-foreground)">
            {formatoNumero(v, decimales)}
          </text>
        ))}
      </svg>
      {frase ? <p className="text-xs text-muted-foreground">{frase}</p> : null}
    </div>
  );
}

export default ViolinPartido;
