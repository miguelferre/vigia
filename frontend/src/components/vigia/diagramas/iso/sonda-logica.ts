/**
 * Comportamiento de la sonda de la portada: la sonda se enchufa (clic o
 * Enter con el foco en la figura), la persona corrige al modelo (clic o `c`),
 * `d` provoca deriva y `r` reinicia. Arranca conectada, en rango y sin
 * deriva. Con `prefers-reduced-motion` la figura queda quieta y encendida.
 * Las teclas se escuchan en el propio `<svg>` (solo con el foco) y no suben a
 * la navegación de la presentación. `montarSonda` devuelve `limpiar`.
 */

import { FUERA } from "./sonda-escena";
import { crearMotor } from "./sonda-motor";

export interface EnlacesSonda {
  /** Texto de estado para la línea accesible bajo la figura. */
  alLeer: (texto: string) => void;
  /** Enciende o apaga el resplandor de fondo. */
  alEncender: (encendida: boolean) => void;
  /** Aviso corto para lectores de pantalla: solo tras una acción de la persona, no en cada decisión. */
  alAnunciar: (texto: string) => void;
}

const hash = (n: number) => {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return s - Math.floor(s);
};

// Historial inicial: doce decisiones con dos correcciones (la figura nace con uso reciente).
const HISTORIAL = [0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0].map(Boolean);

export function montarSonda(svg: SVGSVGElement, enlaces: EnlacesSonda): () => void {
  const motor = crearMotor();
  const $ = (id: string) => svg.querySelector<SVGElement>("#" + id);
  const el = (id: string) => $(id) as SVGElement;
  const sonda = el("so-probe");
  const nodos = [...svg.querySelectorAll<SVGElement>(".nd")];
  const quieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const st = { on: true, mal: false, hist: [...HISTORIAL], ultima: false };

  function trazo(i: number, ms: number) {
    const y0 = 14 + i * 13;
    const mal = st.mal && i === 2;
    let d = "";
    for (let x = 22; x <= 68.01; x += 0.8) {
      const u = x + (ms / 1000) * 20 + i * 11;
      let y = 1.4 * Math.sin(u * 0.45) + 0.5 * Math.sin(u * 1.4);
      if (mal) y = y * 1.5 + 3 * (hash(Math.floor(u * 1.2)) - 0.5) - (x - 22) * 0.05;
      d += `${d ? "L" : "M"}${x.toFixed(1)} ${(y0 - y).toFixed(2)}`;
    }
    return d;
  }
  function marcas() {
    const h = st.on ? st.hist.slice(-16) : [];
    el("so-ticks").innerHTML = h
      .map((c, k) => `<rect class="tick${c ? " corr" : ""}" x="${21 + k * 3.6}" y="${c ? 47.5 : 51}" width="2" height="${c ? 8 : 4.5}" rx=".6"/>`)
      .join("");
  }
  function render() {
    svg.classList.toggle("on", st.on);
    sonda.setAttribute("transform", st.on ? "" : `translate(${FUERA[0].toFixed(2)} ${FUERA[1].toFixed(2)})`);
    ["so-w", "so-wu"].forEach((id) => el(id).classList.toggle("hot", st.on));
    el("so-wr").classList.add("hot");
    el("so-ring").classList.toggle("hot", st.on);
    nodos.forEach((n) => n.classList.toggle("hot", st.on));
    el("so-glass").classList.toggle("hot", st.on);
    el("so-halo").classList.toggle("hot", st.on);
    el("so-alarm").classList.toggle("hot", st.on && st.mal);
    [0, 1, 2].forEach((i) => {
      el("so-f" + i).classList.toggle("mal", st.on && st.mal && i === 2);
      el("so-e" + i).classList.toggle("hot", st.on);
      if (!st.on) el("so-t" + i).setAttribute("d", `M22 ${14 + i * 13}h46`);
      else if (quieto) el("so-t" + i).setAttribute("d", trazo(i, 900));
    });
    el("so-dsig").classList.toggle("oculto", st.ultima);
    el("so-dcor").classList.toggle("oculto", !st.ultima);
    marcas();
    enlaces.alEncender(st.on);
    const corr = st.hist.filter(Boolean).length;
    enlaces.alLeer(
      !st.on
        ? "Sonda desenchufada. Clic en la sonda para conectarla."
        : st.mal
          ? "Deriva fuera de rango: alerta en el monitor."
          : `Sonda conectada: ${st.hist.length} decisiones, ${corr} correcciones.`,
    );
  }
  // La persona decide: sigue al modelo o lo corrige; la decisión viaja al monitor.
  function decide(corrige: boolean) {
    st.ultima = corrige;
    render();
    if (st.on && !quieto) motor.replay($("so-wu-p"));
    if (corrige) motor.flash($("so-ubadge"));
    motor.after(700, () => {
      if (!st.on) return;
      st.hist.push(corrige);
      render();
    });
  }
  const latido = () => {
    nodos.forEach((n) => motor.replay(n));
    motor.after(300, () => motor.replay($("so-wr-p")));
    motor.after(900, () => decide(hash(st.hist.length + 3) < 0.2));
    if (st.on) motor.after(500, () => motor.replay($("so-w-p")));
  };
  const conectar = () => {
    motor.flash(sonda);
    st.on = !st.on;
    if (!st.on) {
      st.mal = false;
      st.hist = [];
    }
    render();
    enlaces.alAnunciar(st.on ? "Sonda conectada." : "Sonda desenchufada.");
  };
  const deriva = () => {
    if (!st.on) {
      enlaces.alLeer("Enchufa antes la sonda.");
      enlaces.alAnunciar("Enchufa antes la sonda.");
      motor.flash(sonda);
      return;
    }
    st.mal = !st.mal;
    render();
    enlaces.alAnunciar(st.mal ? "Deriva fuera de rango: alerta en el monitor." : "Deriva corregida: en rango.");
  };
  const reiniciar = () => {
    st.on = false;
    st.mal = false;
    st.hist = [];
    st.ultima = false;
    render();
    enlaces.alAnunciar("Figura reiniciada: sonda desenchufada.");
  };

  const alClic = (e: Event) => {
    const t = e.target as Element;
    if (t.closest("#so-probe")) conectar();
    else if (t.closest("#so-user")) decide(true);
  };
  const alTeclado = (e: KeyboardEvent) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const acciones: Record<string, () => void> = { "Enter": conectar, "c": () => decide(true), "d": deriva, "r": reiniciar };
    const accion = Object.hasOwn(acciones, e.key) ? acciones[e.key] : undefined;
    if (!accion) return;
    e.preventDefault();
    e.stopPropagation();
    accion();
  };
  svg.addEventListener("click", alClic);
  svg.addEventListener("keydown", alTeclado);

  render();
  if (!quieto) {
    motor.every(2000, latido);
    motor.loop((ts) => {
      if (st.on) [0, 1, 2].forEach((i) => el("so-t" + i).setAttribute("d", trazo(i, ts)));
    });
  }
  return () => {
    svg.removeEventListener("click", alClic);
    svg.removeEventListener("keydown", alTeclado);
    motor.limpiar();
  };
}
