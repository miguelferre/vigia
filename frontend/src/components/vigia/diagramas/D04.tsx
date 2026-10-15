/**
 * Diapositiva 4: variables latentes. A la izquierda, personas que parecen
 * iguales; a la derecha, las mismas personas partidas en subgrupos que el
 * modelo trata distinto, mientras la métrica global no se mueve. Los 52
 * puntos son los de la propuesta (semilla 4), ya redondeados.
 */

import { Ci, Elipse, Figura, Rc, Tx } from "./primitivas";

const ETIQUETA =
  "Variables latentes. Personas que parecen iguales se parten en subgrupos que el modelo trata distinto, mientras la métrica global no se mueve.";

/** Posición de cada persona respecto al centro de su nube (radio 104). */
const PUNTOS: Array<[number, number]> = [
  [-54.9, -82.5], [-21.6, -71.8], [-90.2, -20.5], [55.2, -57.8], [7.6, -46.5], [68.4, 63.8],
  [62.5, -63.8], [-39.6, 26.4], [48.2, 73.8], [22.0, 35.7], [1.2, -67.0], [-5.5, -85.4],
  [9.9, -41.5], [85.0, 15.1], [1.7, -17.9], [20.6, -14.3], [-70.4, -40.5], [-94.4, 26.3],
  [-45.7, 7.2], [-6.0, -32.7], [-18.1, -61.8], [27.6, -46.5], [-30.0, 51.4], [-37.3, 12.2],
  [55.2, 24.0], [-54.6, -35.1], [-67.1, -8.5], [-95.1, 41.0], [-18.6, 92.2], [25.1, 66.1],
  [-43.0, -64.2], [-11.6, -75.6], [-24.6, 96.1], [59.0, -28.6], [-43.6, -83.8], [100.2, -15.8],
  [36.8, -72.9], [-95.5, -1.9], [-78.6, 6.1], [56.9, -18.9], [101.4, -4.6], [-53.7, -18.6],
  [-96.3, -16.4], [-52.3, 81.0], [68.9, -0.3], [-53.6, -60.7], [-55.9, 76.9], [89.0, 13.6],
  [83.4, 32.0], [60.5, 50.9], [-1.2, -84.7], [-60.1, 77.8],
];

const MAYORES: [number, number] = [36, -44];
const INCIDENCIAS: [number, number] = [-40, 46];

function subgrupo(x: number, y: number): "m" | "t" | "mu" {
  if ((x - MAYORES[0]) ** 2 + (y - MAYORES[1]) ** 2 <= 38 ** 2) return "m";
  if ((x - INCIDENCIAS[0]) ** 2 + (y - INCIDENCIAS[1]) ** 2 <= 36 ** 2) return "t";
  return "mu";
}

export function D04({ className }: { className?: string }) {
  return (
    <Figura className={className} etiqueta={ETIQUETA}>
      <Tx x={145} y={28} s={15} w={500} c="mu" a="middle">Personas,</Tx>
      <Tx x={145} y={48} s={15} w={500} c="mu" a="middle">aparentemente homogéneas</Tx>
      <Tx x={455} y={28} s={15} w={500} c="mu" a="middle">Las mismas personas,</Tx>
      <Tx x={455} y={48} s={15} w={500} c="mu" a="middle">clasificadas por subgrupos</Tx>
      {PUNTOS.map(([x, y], i) => (
        <g key={i}>
          <Ci x={145 + x} y={168 + y} r={5} c="mu" solid />
          <Ci x={455 + x} y={168 + y} r={5.5} c={subgrupo(x, y)} solid />
        </g>
      ))}
      <Elipse x={455 + MAYORES[0]} y={168 + MAYORES[1]} rx={46} ry={42} c="m" />
      <Elipse x={455 + INCIDENCIAS[0]} y={168 + INCIDENCIAS[1]} rx={44} ry={40} c="t" />
      <Ci x={352} y={288} r={6} c="m" solid />
      <Tx x={366} y={293} w={600} c="m">mayores de 70</Tx>
      <Ci x={352} y={312} r={6} c="t" solid />
      <Tx x={366} y={317} w={600} c="t">con varias incidencias previas</Tx>
      <Rc x={20} y={344} w={300} h={18} c="v" f="v" r={4} />
      <Tx x={332} y={358} s={15} w={600} c="v">Métrica global: no se mueve</Tx>
      <Rc x={20} y={380} w={110} h={18} c="m" f="m" r={4} />
      <Tx x={142} y={394} s={15} w={600} c="m">Subgrupo «mayores de 70»: cae</Tx>
    </Figura>
  );
}

export default D04;
