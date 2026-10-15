/**
 * Dibujo de la sonda de Vigía (portada, diapositiva 1): un modelo de IA con
 * una red neuronal en la tapa, una sonda enchufada, una persona que usa el
 * modelo desde un terminal y un monitor con las constantes. Solo genera el
 * marcado; el comportamiento vive en `sonda-logica.ts`.
 *
 *   cajas               x    y    z    w    d    h
 *   modelo             28   34    7   84   84   66   puerto en FRONT (y=118)
 *   sonda              92  118   26   10   32   10
 *   persona             2  146    7   17   10   61   pies en (4, 150)
 *   terminal           24  138    7   44   14   30
 *   monitor           160  128    7   86   16   78
 */

import { CUERPO, ico } from "./sonda-iconos";
import { frame, slits } from "./nucleo";

const PZ = 7;
const K = frame(
  [[28, 34, 73], [28, 34, 7], [112, 34, 73], [112, 34, 7], [28, 118, 7], [160, 128, 85], [246, 144, 85], [246, 182, 7], [0, 146, 7], [0, 155, 7], [4, 150, 75], [58, 182, 7], [176, 182, 7]],
  0.08,
);
const { P, D, TOP, FRONT, SIDE, box, path } = K;

/** Desplazamiento de la sonda desenchufada. */
export const FUERA = D(0, 16, 0);
export const VIEWBOX = K.viewBox;

const cable = (id: string, d: string) =>
  `<path class="wire-under" d="${d}"/><path id="${id}" class="wire" d="${d}"/><path id="${id}-p" class="pulse" pathLength="1000" d="${d}"/>`;

function modelo() {
  let s = box(28, 34, PZ, 84, 84, 66, 5);
  s += `<g transform="${FRONT(28, 118, 73)}">${slits(8, 76, 4, 8, 34)}
    <text class="label" x="8" y="46" font-size="4.6" letter-spacing=".7">MODELO</text>
    <rect class="face recess" x="60" y="38" width="16" height="11" rx="1.5"/></g>`;
  s += `<g transform="${SIDE(112, 118, 73)}">${slits(8, 76, 6, 8, 58)}</g>`;
  const L: [number, number[]][] = [[18, [18, 32, 46, 60]], [42, [14, 28, 42, 56, 70]], [66, [30, 50]]];
  let nn = "";
  let nd = "";
  for (let a = 0; a < 2; a++)
    for (const v0 of L[a][1])
      for (const v1 of L[a + 1][1]) nn += `<line class="nn" x1="${L[a][0]}" y1="${v0}" x2="${L[a + 1][0]}" y2="${v1}"/>`;
  L.forEach(([u, vs], li) => vs.forEach((v) => (nd += `<circle class="led nd" cx="${u}" cy="${v}" r="2.2" style="animation-delay:${li * 120}ms"/>`)));
  return s + `<g transform="${TOP(28, 34, 73)}"><rect class="face recess" x="8" y="8" width="68" height="68" rx="3"/>${nn}${nd}</g>`;
}

function persona() {
  const [fx, fy] = P(4, 150, PZ);
  return `<g class="press" id="so-user"><g transform="translate(${fx.toFixed(2)} ${fy.toFixed(2)})">
    <ellipse class="detail" cx="0" cy="0" rx="14" ry="4"/>
    <path class="face persona" d="${CUERPO}"/>
    <circle class="face persona" cx="0" cy="-54" r="9"/>
    <circle id="so-ubadge" class="led" cx="3.5" cy="-35" r="1.6"/></g></g>`;
}

function terminal() {
  return (
    box(24, 138, PZ, 44, 14, 30, 3) +
    `<g transform="${FRONT(24, 152, PZ + 30)}"><rect id="so-tg" class="face glass hot" x="3" y="3" width="38" height="19" rx="1.5"/>
    <g id="so-dsig">${ico("sigue", 14, 4.5, 16, "vivo")}</g><g id="so-dcor" class="oculto">${ico("corrige", 14, 4.5, 16, "vivo")}</g></g>`
  );
}

function sonda() {
  return `<g class="press" id="so-probe">
    ${box(94, 118, 28, 6, 6, 6, 1)}${box(92, 124, 26, 10, 8, 10, 2)}
    <g transform="${TOP(92, 124, 36)}"><rect id="so-ring" class="led" x="1.5" y="1.5" width="7" height="5" rx="2"/></g>
    ${box(93, 132, 27, 8, 18, 8, 3)}<g transform="${SIDE(101, 150, 35)}">${slits(2, 16, 3, 1.5, 6.5)}</g></g>`;
}

function monitor() {
  let filas = "";
  (["equidad", "calidad", "deriva"] as const).forEach((n, i) => {
    const y = 15 + i * 13;
    filas += `<g id="so-f${i}">${ico(n, 7, y - 6, 10, "mon")}<path id="so-t${i}" class="trace" d="M22 ${y - 1}h46"/>
      <circle id="so-e${i}" class="led" cx="76" cy="${y - 1}" r="2.6"/></g>`;
  });
  return (
    box(160, 128, PZ, 86, 16, 78, 4) +
    `<g transform="${FRONT(160, 144, 85)}">
    <rect id="so-halo" class="halo" x="0" y="2" width="86" height="58" filter="url(#sonda-bloom)"/>
    <rect id="so-glass" class="face glass" x="3" y="4" width="80" height="54" rx="2.5"/>${filas}
    <path class="detail" d="M7 46H79"/>${ico("persona", 7, 47, 10, "mon")}<g id="so-ticks"></g>
    <text class="label" x="5" y="68" font-size="3.8" letter-spacing=".6">VIGÍA · CONSTANTES</text>
    <circle id="so-alarm" class="led" cx="78" cy="66.6" r="2.4"/></g>` +
    `<g transform="${SIDE(246, 144, 85)}">${slits(4, 12, 4, 8, 70)}</g>`
  );
}

/** Marcado completo de la escena, de atrás hacia delante. */
export function escena(): string {
  const dr = path([[46, 118, PZ + 0.5], [46, 138, PZ + 0.5]]);
  const dw = path([[97, 150, 31], [97, 166, 31], [97, 166, PZ + 0.5], [200, 166, PZ + 0.5], [200, 144, PZ + 0.5]]);
  const du = path([[58, 144, PZ + 0.5], [58, 182, PZ + 0.5], [176, 182, PZ + 0.5], [176, 144, PZ + 0.5]]);
  return modelo() + cable("so-wr", dr) + cable("so-w", dw) + persona() + cable("so-wu", du) + terminal() + sonda() + monitor();
}
