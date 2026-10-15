/**
 * Primitivas de las figuras 2 a 10 de la presentación: un lienzo de 600 x 420 y ocho piezas
 * pequeñas (texto, rectángulo, círculo, elipse, trazo con marcador, icono,
 * medalla y barra). Cada pieza recibe un tono (`Tono`), no un color: el mapa de abajo
 * lo traduce a los tokens de la aplicación, así que las figuras siguen el
 * tema claro y el oscuro sin color literal.
 *
 * Papeles: violeta (`v`, `--chart-1`) es Vigía y lo que se mide; verde azulado
 * (`t`, `--chart-3`) son las personas y lo correcto; magenta (`m`,
 * `--chart-2`) es el problema; `i` es el texto principal y `mu` el secundario.
 *
 * El texto en color no usa el token tal cual (el verde azulado da 3,2 : 1 en
 * claro): `Figura` publica sobre el `<svg>` las variables `--f-v`, `--f-t` y
 * `--f-m`, que mezclan el token con el color de texto al 65 %, y los tintes de
 * fondo (`--f-vt`, `--f-tt`, `--f-mt`) al 12 % sobre `--card`. Con eso todo
 * texto en color llega a 4,5 : 1 sobre el fondo, la tarjeta y su tinte, en los
 * dos temas (lo comprueba `test_textos_interfaz_r8c_p2.py`).
 */

import type { CSSProperties, ReactNode } from "react";

import { ICONOS, type NombreIcono } from "./iconos-figuras";

export type Tono = "v" | "t" | "m" | "i" | "mu" | "bg";

/** Trazo y relleno sólido de cada tono. */
const TRAZO: Record<Tono, string> = {
  v: "var(--chart-1)",
  t: "var(--chart-3)",
  m: "var(--chart-2)",
  i: "var(--foreground)",
  mu: "var(--muted-foreground)",
  bg: "var(--card)",
};

/** Color del texto de cada tono (los tres colores, mezclados: ver arriba). */
const TEXTO: Record<Tono, string> = {
  v: "var(--f-v)",
  t: "var(--f-t)",
  m: "var(--f-m)",
  i: "var(--foreground)",
  mu: "var(--muted-foreground)",
  bg: "var(--card)",
};

/** Relleno suave de cada tono. */
const TINTE: Record<Tono, string> = {
  v: "var(--f-vt)",
  t: "var(--f-tt)",
  m: "var(--f-mt)",
  i: "var(--card)",
  mu: "var(--card)",
  bg: "var(--card)",
};

const VARIABLES = {
  "--f-v": "color-mix(in srgb, var(--chart-1) 65%, var(--foreground))",
  "--f-t": "color-mix(in srgb, var(--chart-3) 65%, var(--foreground))",
  "--f-m": "color-mix(in srgb, var(--chart-2) 65%, var(--foreground))",
  "--f-vt": "color-mix(in srgb, var(--chart-1) 12%, var(--card))",
  "--f-tt": "color-mix(in srgb, var(--chart-3) 12%, var(--card))",
  "--f-mt": "color-mix(in srgb, var(--chart-2) 12%, var(--card))",
} as CSSProperties;

const MARCADORES: Array<[string, Tono]> = [
  ["i", "mu"],
  ["v", "v"],
  ["t", "t"],
  ["m", "m"],
];

/** Lienzo de la figura: define las variables de color y las puntas de flecha. */
export function Figura({ className, etiqueta, children }: { className?: string; etiqueta: string; children: ReactNode }) {
  return (
    <svg viewBox="0 0 600 420" width="100%" className={className} style={VARIABLES} role="img" aria-label={etiqueta}>
      <defs>
        {MARCADORES.map(([id, tono]) => (
          <marker key={id} id={`vg-ar-${id}`} markerWidth={8} markerHeight={8} refX={7} refY={4} orient="auto-start-reverse">
            <path d="M0 0L8 4 0 8z" fill={TRAZO[tono]} />
          </marker>
        ))}
      </defs>
      {children}
    </svg>
  );
}

/** Texto de una línea. `s` tamaño, `w` peso, `c` tono, `a` anclaje. */
export function Tx({ x, y, s = 16, w = 400, c = "i", a = "start", children }: { x: number; y: number; s?: number; w?: number; c?: Tono; a?: "start" | "middle" | "end"; children: string }) {
  return (
    <text x={x} y={y} fontSize={s} fontWeight={w} fill={TEXTO[c]} textAnchor={a}>
      {children}
    </text>
  );
}

/** Rectángulo con trazo del tono `c` y relleno suave opcional del tono `f`. */
export function Rc({ x, y, w, h, c = "i", f, r = 8, sw = 1.5, dash }: { x: number; y: number; w: number; h: number; c?: Tono; f?: Tono; r?: number; sw?: number; dash?: string }) {
  return <rect x={x} y={y} width={w} height={h} rx={r} fill={f ? TINTE[f] : "none"} stroke={TRAZO[c]} strokeWidth={sw} strokeDasharray={dash} />;
}

/** Círculo: `solid` lo rellena del color del trazo; `f` lo rellena con el tinte. */
export function Ci({ x, y, r, c = "i", f, sw = 1.5, solid }: { x: number; y: number; r: number; c?: Tono; f?: Tono; sw?: number; solid?: boolean }) {
  const fill = solid ? TRAZO[c] : f ? TINTE[f] : "none";
  return <circle cx={x} cy={y} r={r} fill={fill} stroke={TRAZO[c]} strokeWidth={sw} />;
}

/** Elipse de trazo discontinuo (los subgrupos de la diapositiva 4). */
export function Elipse({ x, y, rx, ry, c }: { x: number; y: number; rx: number; ry: number; c: Tono }) {
  return <ellipse cx={x} cy={y} rx={rx} ry={ry} fill="none" stroke={TRAZO[c]} strokeWidth={1.5} strokeDasharray="5 4" />;
}

/** Trazo (`c="none"` lo deja sin línea): `m` es la punta de flecha del final y `f` un relleno suave. */
export function Tr({ d, c = "mu", f, sw = 2, dash, m }: { d: string; c?: Tono | "none"; f?: Tono; sw?: number; dash?: string; m?: "i" | "v" | "t" | "m" }) {
  return (
    <path
      d={d}
      fill={f ? TINTE[f] : "none"}
      stroke={c === "none" ? "none" : TRAZO[c]}
      strokeWidth={sw}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={dash}
      markerEnd={m ? `url(#vg-ar-${m})` : undefined}
    />
  );
}

/** Icono de línea de 24 x 24 escalado a `z`, con su esquina superior izquierda en (x, y). */
export function Ic({ n, x, y, z = 24, c = "i", sw = 1.8 }: { n: NombreIcono; x: number; y: number; z?: number; c?: Tono; sw?: number }) {
  const k = z / 24;
  return (
    <g
      transform={`translate(${x} ${y}) scale(${k})`}
      fill="none"
      stroke={TRAZO[c]}
      strokeWidth={Number((sw / k).toFixed(2))}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {ICONOS[n]}
    </g>
  );
}

/** Círculo con tinte y un icono centrado en (x, y). */
export function Medalla({ x, y, n, c = "v", r = 28, z = 28 }: { x: number; y: number; n: NombreIcono; c?: Tono; r?: number; z?: number }) {
  return (
    <>
      <Ci x={x} y={y} r={r} c={c} f={c} />
      <Ic n={n} x={x - z / 2} y={y - z / 2} z={z} c={c} />
    </>
  );
}

/** Barra rellena del color del tono, sin trazo. */
export function Barra({ x, y, w, h, r, c }: { x: number; y: number; w: number; h: number; r: number; c: Tono }) {
  return <rect x={x} y={y} width={w} height={h} rx={r} fill={TRAZO[c]} />;
}
