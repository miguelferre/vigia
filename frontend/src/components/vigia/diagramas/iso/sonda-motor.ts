/**
 * Utilidades de tiempo de la figura (equivalen a la API de las figuras con
 * brillo): temporizadores, bucle de animación, destello y repetición de una
 * animación de una sola vez. Todo lo que se arranca se anota para que
 * `limpiar()` lo pare al desmontar la figura.
 */

type Parpadeo = HTMLElement | SVGElement;

export function crearMotor() {
  const timeouts = new Set<number>();
  const intervalos = new Set<number>();
  const marcos = new Set<number>();
  const destellos = new Map<Parpadeo, number[]>();

  const after = (ms: number, fn: () => void) => {
    const t = window.setTimeout(() => {
      timeouts.delete(t);
      fn();
    }, ms);
    timeouts.add(t);
    return t;
  };
  const every = (ms: number, fn: () => void) => {
    const t = window.setInterval(fn, ms);
    intervalos.add(t);
    return t;
  };
  const loop = (fn: (ts: number) => void) => {
    let vivo = true;
    let id = 0;
    const f = (ts: number) => {
      if (!vivo) return;
      fn(ts);
      marcos.delete(id);
      id = requestAnimationFrame(f);
      marcos.add(id);
    };
    id = requestAnimationFrame(f);
    marcos.add(id);
    return () => {
      vivo = false;
      cancelAnimationFrame(id);
      marcos.delete(id);
    };
  };
  /** Enciende un pulsable un instante (hundido y con brillo) y lo apaga. */
  const flash = (el: Parpadeo | null, ms = 160) => {
    if (!el) return;
    destellos.get(el)?.forEach((t) => window.clearTimeout(t));
    el.classList.add("down", "lit");
    const t1 = window.setTimeout(() => el.classList.remove("down"), 110);
    const t2 = window.setTimeout(() => el.classList.remove("lit"), ms);
    destellos.set(el, [t1, t2]);
  };
  /** Reinicia una animación CSS de una sola vez. */
  const replay = (el: Parpadeo | null, cls = "go") => {
    if (!el) return;
    el.classList.remove(cls);
    void el.getBoundingClientRect();
    el.classList.add(cls);
  };
  const limpiar = () => {
    timeouts.forEach((t) => clearTimeout(t));
    intervalos.forEach((t) => clearInterval(t));
    marcos.forEach((id) => cancelAnimationFrame(id));
    destellos.forEach((ts) => ts.forEach((t) => clearTimeout(t)));
    timeouts.clear();
    intervalos.clear();
    marcos.clear();
    destellos.clear();
  };
  return { after, every, loop, flash, replay, limpiar };
}

export type Motor = ReturnType<typeof crearMotor>;
