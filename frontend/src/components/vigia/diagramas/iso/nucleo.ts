/**
 * Núcleo isométrico de las figuras con brillo (extracto de lo que usa la
 * sonda de la portada): proyección de 30 grados, planos, caja redondeada,
 * trazos 3D, encuadre y rendijas. Genera cadenas de SVG; las clases
 * (`face`, `top`, `detail`) las estila `sonda.css` bajo `.iso-sonda`.
 */

export type Punto3 = [number, number, number];

const C = Math.cos(Math.PI / 6);
const S = Math.sin(Math.PI / 6);

export function nucleo(OX: number, OY: number) {
  const P = (x: number, y: number, z: number): [number, number] => [(x - y) * C + OX, (x + y) * S - z + OY];
  const D = (x: number, y: number, z: number): [number, number] => [(x - y) * C, (x + y) * S - z];
  const plane = (O: Punto3, U: Punto3, V: Punto3) => {
    const o = P(...O);
    const u = D(...U);
    const v = D(...V);
    return `matrix(${u[0]} ${u[1]} ${v[0]} ${v[1]} ${o[0]} ${o[1]})`;
  };
  const TOP = (x: number, y: number, z: number) => plane([x, y, z], [1, 0, 0], [0, 1, 0]);
  const FRONT = (x: number, y: number, z: number) => plane([x, y, z], [1, 0, 0], [0, 0, -1]);
  const SIDE = (x: number, y: number, z: number) => plane([x, y, z], [0, -1, 0], [0, 0, -1]);

  // Caja redondeada: tapa redondeada y una pared continua por el contorno visible.
  const redondeada = (x: number, y: number, z: number, w: number, d: number, h: number, radio: number) => {
    const r = Math.min(radio, w / 2, d / 2);
    const n = 10;
    const z1 = z + h;
    const q = Math.PI / 4;
    const H = Math.PI / 2;
    const arco = (cx: number, cy: number, a0: number, a1: number) => {
      const o: [number, number][] = [];
      for (let i = 0; i <= n; i++) {
        const a = a0 + ((a1 - a0) * i) / n;
        o.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
      }
      return o;
    };
    const anillo = [...arco(x + w - r, y + r, -H, 0), ...arco(x + w - r, y + d - r, 0, H), ...arco(x + r, y + d - r, H, 2 * H), ...arco(x + r, y + r, 2 * H, 3 * H)];
    const vis = [...arco(x + w - r, y + r, -q, 0), ...arco(x + w - r, y + d - r, 0, H), ...arco(x + r, y + d - r, H, 3 * q)];
    const d3 = (pts: Punto3[]) => "M" + pts.map((p) => P(...p).map((v) => v.toFixed(2)).join(" ")).join("L") + "Z";
    const pared: Punto3[] = [...vis.map(([a, b]): Punto3 => [a, b, z]), ...vis.slice().reverse().map(([a, b]): Punto3 => [a, b, z1])];
    return `<path class="face" d="${d3(pared)}"/><path class="face top" d="${d3(anillo.map(([a, b]): Punto3 => [a, b, z1]))}"/>`;
  };
  const rect = (t: string, w: number, h: number, r = 0, cls = "face") =>
    `<g transform="${t}"><rect class="${cls}" width="${w}" height="${h}" rx="${r}"/></g>`;
  const box = (x: number, y: number, z: number, w: number, d: number, h: number, r = 0) =>
    r > 0
      ? redondeada(x, y, z, w, d, h, r)
      : rect(SIDE(x + w, y + d, z + h), d, h) + rect(FRONT(x, y + d, z + h), w, h) + rect(TOP(x, y, z + h), w, d, 0, "face top");
  const path = (pts: Punto3[]) => "M" + pts.map((p) => P(...p).map((n) => n.toFixed(2)).join(" ")).join("L");
  return { P, D, plane, TOP, FRONT, SIDE, rect, box, path };
}

/** Encuadra una escena: recibe sus esquinas 3D extremas y devuelve el núcleo con su `viewBox`. */
export function frame(puntos: Punto3[], margen = 0.09, aspecto = 4 / 3) {
  const d = puntos.map(([x, y, z]) => [(x - y) * C, (x + y) * S - z] as const);
  const x0 = Math.min(...d.map((p) => p[0]));
  const x1 = Math.max(...d.map((p) => p[0]));
  const y0 = Math.min(...d.map((p) => p[1]));
  const y1 = Math.max(...d.map((p) => p[1]));
  const m = margen * Math.max(x1 - x0, y1 - y0);
  let w = x1 - x0 + 2 * m;
  let h = y1 - y0 + 2 * m;
  let ox = m - x0;
  let oy = m - y0;
  if (w / h < aspecto) {
    const nw = h * aspecto;
    ox += (nw - w) / 2;
    w = nw;
  } else {
    const nh = w / aspecto;
    oy += (nh - h) / 2;
    h = nh;
  }
  return { ...nucleo(ox, oy), viewBox: `0 0 ${w.toFixed(1)} ${h.toFixed(1)}` };
}

/** Rendijas verticales repetidas en un grupo local de una cara. */
export function slits(a0: number, a1: number, paso: number, b0: number, b1: number) {
  let s = "";
  for (let a = a0; a <= a1 + 1e-6; a += paso) s += `<line class="detail" x1="${a}" y1="${b0}" x2="${a}" y2="${b1}"/>`;
  return s;
}
