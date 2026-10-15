/**
 * Matemática pura del violín «lote a lote»:
 * densidad por tramo, mediana de datos agrupados, silueta por interpolación
 * cúbica monótona (PCHIP) y ticks "bonitos" del eje. Partido de
 * `violin-lote-a-lote-datos.ts` (que se acercaba a 9 KB): ese fichero se
 * queda con los tipos y `prepararViolines`, este con el cálculo numérico.
 */

/** Densidad por tramo (recuento / n / anchura); `[]` si los datos no cuadran. */
export function densidadPorTramo(edges: number[], counts: number[]): number[] {
  if (edges.length !== counts.length + 1) return [];
  const n = counts.reduce((a, b) => a + b, 0);
  if (n === 0) return [];
  const anchuras = counts.map((_, i) => edges[i + 1] - edges[i]);
  if (anchuras.some((a) => !(a > 0))) return [];
  return counts.map((c, i) => c / n / anchuras[i]);
}

/** Mediana de datos agrupados: interpolación lineal en el tramo donde la acumulada llega a n/2. */
export function medianaDeTramos(edges: number[], counts: number[]): number | null {
  if (edges.length !== counts.length + 1 || counts.length === 0) return null;
  const n = counts.reduce((a, b) => a + b, 0);
  if (n === 0) return null;
  const mitad = n / 2;
  let acumulado = 0;
  for (let i = 0; i < counts.length; i++) {
    const previo = acumulado;
    acumulado += counts[i];
    if (acumulado >= mitad) {
      const ancho = edges[i + 1] - edges[i];
      if (!(ancho > 0) || counts[i] === 0) return edges[i];
      return edges[i] + ((mitad - previo) / counts[i]) * ancho;
    }
  }
  return edges[edges.length - 1];
}

function signo(v: number): number {
  return v > 0 ? 1 : v < 0 ? -1 : 0;
}

/** Pendiente PCHIP de un extremo (Fritsch-Carlson), con el ajuste que preserva la monotonía. */
function pendienteExtremo(h0: number, h1: number, d0: number, d1: number): number {
  const m = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1);
  if (signo(m) !== signo(d0)) return 0;
  if (signo(d0) !== signo(d1) && Math.abs(m) > 3 * Math.abs(d0)) return 3 * d0;
  return m;
}

/** Pendientes PCHIP en cada punto de control: media armónica ponderada, cero donde cambia el signo. */
function pendientesPchip(xs: number[], ys: number[]): number[] {
  const n = xs.length;
  const m = new Array(n).fill(0);
  if (n < 2) return m;
  const h: number[] = [];
  const d: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    h.push(xs[i + 1] - xs[i]);
    d.push((ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]));
  }
  if (n === 2) {
    m[0] = d[0];
    m[1] = d[0];
    return m;
  }
  for (let i = 1; i < n - 1; i++) {
    const dPrev = d[i - 1];
    const dCur = d[i];
    if (dPrev === 0 || dCur === 0 || signo(dPrev) !== signo(dCur)) {
      m[i] = 0;
    } else {
      const w1 = 2 * h[i] + h[i - 1];
      const w2 = h[i] + 2 * h[i - 1];
      m[i] = (w1 + w2) / (w1 / dPrev + w2 / dCur);
    }
  }
  m[0] = pendienteExtremo(h[0], h[1], d[0], d[1]);
  m[n - 1] = pendienteExtremo(h[n - 2], h[n - 3], d[n - 2], d[n - 3]);
  return m;
}

/** Evalúa el Hermite cúbico por tramos definido por `(xs, ys, m)` en `x`. */
function evaluarHermite(xs: number[], ys: number[], m: number[], x: number): number {
  let i = 0;
  while (i < xs.length - 2 && x > xs[i + 1]) i++;
  const h = xs[i + 1] - xs[i];
  const t = h === 0 ? 0 : (x - xs[i]) / h;
  const t2 = t * t;
  const t3 = t2 * t;
  const h00 = 2 * t3 - 3 * t2 + 1;
  const h10 = t3 - 2 * t2 + t;
  const h01 = -2 * t3 + 3 * t2;
  const h11 = t3 - t2;
  return h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1];
}

/**
 * Silueta suavizada de una variable: puntos de control en (borde inicial, 0),
 * (punto medio de cada tramo, densidad) y (borde final, 0), interpolados con
 * PCHIP y muestreados en `muestras` valores equiespaciados. Nunca negativa.
 */
export function siluetaMonotona(
  edges: number[],
  densidades: number[],
  muestras = 80,
): { valor: number; densidad: number }[] {
  if (edges.length < 2 || densidades.length !== edges.length - 1) return [];
  const xs: number[] = [edges[0]];
  const ys: number[] = [0];
  for (let i = 0; i < densidades.length; i++) {
    xs.push((edges[i] + edges[i + 1]) / 2);
    ys.push(densidades[i]);
  }
  xs.push(edges[edges.length - 1]);
  ys.push(0);
  const m = pendientesPchip(xs, ys);
  const xMin = xs[0];
  const xMax = xs[xs.length - 1];
  const puntos: { valor: number; densidad: number }[] = [];
  for (let j = 0; j < muestras; j++) {
    const valor = muestras === 1 ? xMin : xMin + ((xMax - xMin) * j) / (muestras - 1);
    puntos.push({ valor, densidad: Math.max(0, evaluarHermite(xs, ys, m, valor)) });
  }
  return puntos;
}

/** 0 decimales si el rango del eje es de 20 o más; 1 si no. */
export function decimalesDelEje(min: number, max: number): number {
  return max - min >= 20 ? 0 : 1;
}

/** Ticks "bonitos" (paso 1, 2 o 5 × 10^k) que den entre 4 y 6 dentro de `[min, max]`. */
export function dominioYTicks(min: number, max: number): { min: number; max: number; ticks: number[] } {
  if (!(max > min)) return { min, max, ticks: [] };
  const rango = max - min;
  const exp = Math.floor(Math.log10(rango));
  const candidatos = new Set<number>();
  for (let k = exp - 2; k <= exp + 2; k++) {
    for (const base of [1, 2, 5]) candidatos.add(base * Math.pow(10, k));
  }
  let paso = rango;
  for (const c of Array.from(candidatos).sort((a, b) => a - b)) {
    const primero = Math.ceil(min / c) * c;
    const ultimo = Math.floor(max / c) * c;
    if (ultimo < primero) continue;
    const cuenta = Math.round((ultimo - primero) / c) + 1;
    if (cuenta >= 4 && cuenta <= 6) {
      paso = c;
      break;
    }
  }
  const primero = Math.ceil(min / paso) * paso;
  const ultimo = Math.floor(max / paso) * paso;
  const ticks: number[] = [];
  for (let v = primero; v <= ultimo + paso * 1e-9; v += paso) {
    ticks.push(Math.round(v * 1e9) / 1e9);
  }
  return { min, max, ticks };
}
