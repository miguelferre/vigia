/**
 * SVG del violín «lote a lote»: ejes, rejilla,
 * mediana discontinua por línea base, un violín por hueco y su tooltip
 * (hover y foco). Geometría del artboard aprobado (gen_violin.py,
 * `svg_lote_a_lote`): márgenes 46/150/14/44, alto 300, barriga al 42 %.
 */

import { useMemo, useRef, useState } from "react";

import { formatoCorto, formatoNumero } from "@/lib/metrics";
import { decimalesDelEje, dominioYTicks } from "./violin-silueta";
import { caminoViolin, lineasTooltip } from "./violin-lote-a-lote-datos";
import type { ViolinPreparado, TramoMediana } from "./violin-lote-a-lote-datos";
import { colorPsi, etiquetaFaseCorta } from "./violin-svg-datos";
import { ViolinDesbordamiento } from "./ViolinDesbordamiento";

export interface ViolinSvgProps {
  violines: ViolinPreparado[];
  tramosMediana: TramoMediana[];
  densidadMax: number;
  min: number;
  max: number;
  ancho: number;
  alto?: number;
  featureLabel: string;
}

const IZQ = 46,
  DER = 150,
  ARRIBA = 14,
  ABAJO = 44,
  HUECO_MIN = 44;

export function ViolinSvg({ violines, tramosMediana, densidadMax, min, max, ancho, alto = 300, featureLabel }: ViolinSvgProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollX, setScrollX] = useState(0);
  const [activo, setActivo] = useState<number | null>(null);

  const n = violines.length;
  const y0 = alto - ABAJO;
  const y1 = ARRIBA;
  const huecoNatural = n > 0 ? (ancho - IZQ - DER) / n : 0;
  const hueco = Math.max(HUECO_MIN, huecoNatural);
  const svgAncho = Math.max(ancho, IZQ + DER + hueco * n);
  const escala = densidadMax > 0 ? (hueco * 0.42) / densidadMax : 0;
  const decimales = decimalesDelEje(min, max);
  const { ticks } = dominioYTicks(min, max);
  // `svgAncho` crece sin tope con `n` y el desplazamiento
  // horizontal no se veía; degradado y flecha en el borde que todavía
  // esconde lotes, a cada lado según la posición del scroll.
  const desborda = svgAncho > ancho + 1;
  const alInicio = scrollX <= 1;
  const alFinal = scrollX + ancho >= svgAncho - 1;

  const yDe = (v: number) => (max > min ? y0 - ((v - min) / (max - min)) * (y0 - y1) : y0);

  const basePorGrupo = useMemo(() => {
    const mapa = new Map<number, number | null>();
    for (const v of violines) if (v.tipo === "base") mapa.set(v.grupo, v.mediana);
    return mapa;
  }, [violines]);

  const flagsFase = useMemo(() => {
    const flags: boolean[] = [];
    let ultimaFaseLote: string | null = null;
    for (const v of violines) {
      let mostrar = false;
      if (v.tipo === "lote") {
        if (v.fase !== null && v.fase !== ultimaFaseLote) mostrar = true;
        ultimaFaseLote = v.fase;
      }
      flags.push(mostrar);
    }
    return flags;
  }, [violines]);

  /** Junto al violín `i`: a su derecha si caben unos 220 px, si no a su izquierda. */
  const posicionTooltip = (i: number) => {
    const cx = IZQ + hueco * (i + 0.5) - scrollX;
    const aDerecha = cx + hueco / 2 + 8 + 220 <= ancho;
    return aDerecha
      ? { left: cx + hueco / 2 + 8, transform: undefined }
      : { left: cx - hueco / 2 - 8, transform: "translateX(-100%)" };
  };

  if (n === 0) return null;

  return (
    <div className="relative">
      <div ref={scrollRef} className="overflow-x-auto" onScroll={() => setScrollX(scrollRef.current?.scrollLeft ?? 0)}>
        <svg width={svgAncho} height={alto} viewBox={`0 0 ${svgAncho} ${alto}`} aria-label={`${featureLabel}, un violín por lote`}>
          {ticks.map((v) => {
            const y = yDe(v);
            return (
              <g key={`tick-${v}`}>
                <line x1={IZQ} y1={y} x2={svgAncho - DER} y2={y} stroke="var(--line)" />
                <text x={IZQ - 8} y={y + 3.5} fontSize={10} fill="var(--muted-foreground)" textAnchor="end">
                  {formatoCorto(v, decimales)}
                </text>
              </g>
            );
          })}

          {tramosMediana.map((tramo, idx) => {
            const y = yDe(tramo.mediana);
            const xDesde = IZQ + hueco * (tramo.desde + 0.5);
            const xHasta = IZQ + hueco * (tramo.hasta + 1);
            // Solo la última línea base lleva texto (a la derecha, como el artboard):
            // dentro del gráfico cualquier etiqueta cae sobre los violines. Las
            // anteriores se leen en la leyenda (trazo discontinuo) y en su tooltip.
            const esUltimo = idx === tramosMediana.length - 1;
            const texto = `${tramo.etiqueta} ${formatoCorto(tramo.mediana, decimales)}`;
            return (
              <g key={`mediana-${tramo.grupo}`}>
                <line x1={xDesde} y1={y} x2={xHasta} y2={y} stroke="var(--chart-3)" strokeWidth={1} strokeDasharray="4 3" />
                {esUltimo ? (
                  <text x={svgAncho - DER + 8} y={y + 3.5} fontSize={10} fill="var(--chart-3)">
                    {texto}
                  </text>
                ) : null}
              </g>
            );
          })}

          <line x1={IZQ} y1={y0} x2={svgAncho - DER} y2={y0} stroke="var(--border)" />

          {violines.map((v, i) => {
            const cx = IZQ + hueco * (i + 0.5);
            const color = v.tipo === "base" ? "var(--chart-3)" : "var(--chart-1)";
            const opacidad = v.tipo === "base" ? 0.55 : 0.35;
            const cambio = v.lectura !== null && v.lectura !== "estable";
            const grosor = v.tipo === "lote" && cambio ? 2 : 1.5;
            const puntos = v.silueta.map((p) => ({ x: p.densidad * escala, y: yDe(p.valor) }));
            const medianaBase = basePorGrupo.get(v.grupo) ?? null;
            const lineas = lineasTooltip(v, medianaBase, decimales);
            return (
              <g
                key={v.clave}
                role="img"
                tabIndex={0}
                aria-label={lineas.join(". ")}
                onMouseEnter={() => setActivo(i)}
                onMouseLeave={() => setActivo(null)}
                onFocus={() => setActivo(i)}
                onBlur={() => setActivo(null)}
              >
                <path d={caminoViolin(cx, puntos)} fill={color} fillOpacity={opacidad} stroke={color} strokeWidth={grosor} />
                {v.mediana !== null ? (
                  <circle cx={cx} cy={yDe(v.mediana)} r={3} fill="var(--card)" stroke={color} strokeWidth={2} />
                ) : null}
                <text x={cx} y={alto - 28} fontSize={11} fontWeight={600} fill="var(--foreground)" textAnchor="middle">
                  {v.etiqueta}
                </text>
                {v.tipo === "base" ? (
                  <text x={cx} y={alto - 14} fontSize={10} fill="var(--muted-foreground)" textAnchor="middle">
                    n {formatoNumero(v.n, 0)}
                  </text>
                ) : (
                  <text x={cx} y={alto - 14} fontSize={10} textAnchor="middle" fill={colorPsi(v)} fontWeight={cambio ? 600 : 400}>
                    PSI {formatoNumero(v.psi, 2)}
                  </text>
                )}
                {flagsFase[i] && v.fase !== null ? (
                  <text x={cx} y={ARRIBA + 2} fontSize={9} fill="var(--muted-foreground)" textAnchor="middle">
                    <title>{v.fase}</title>
                    {hueco >= 72 ? v.fase : etiquetaFaseCorta(v.fase, hueco)}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
      </div>

      <ViolinDesbordamiento desborda={desborda} alInicio={alInicio} alFinal={alFinal} />

      {activo !== null && violines[activo] ? (
        // Al lado del violín activo (a su derecha; a su izquierda si no cabe) y a la
        // altura del margen superior: dentro del gráfico, nunca fuera de la tarjeta.
        <div
          className="pointer-events-none absolute z-10 flex min-w-44 flex-col gap-1 rounded-md p-2.5 text-xs"
          style={{
            left: posicionTooltip(activo).left,
            top: ARRIBA + 4,
            transform: posicionTooltip(activo).transform,
            background: "var(--card)",
            color: "var(--card-foreground)",
            boxShadow: "var(--elevation-pop)",
          }}
        >
          {lineasTooltip(violines[activo], basePorGrupo.get(violines[activo].grupo) ?? null, decimales).map((linea, i) => (
            <p key={i} className={i === 0 ? "font-semibold" : undefined}>
              {linea}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default ViolinSvg;
