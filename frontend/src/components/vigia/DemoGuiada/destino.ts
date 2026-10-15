/**
 * A qué pantalla lleva cada paso de la demo guiada y cómo se llega. `destino.ruta` del contenido puede llevar `:id`
 * (proyecto, o alerta si la ruta es `/alertas/:id`) y `:batch` (lote de la
 * fase que el paso necesita); los pasos con precarga (`crear-modelo`,
 * `subir-datos`, la anotación del diario, `fila`) añaden la query que fija
 * el contrato (`contrato.ts`) y el laboratorio y las diapositivas se
 * resuelven en `/demo`. La ruta del contenido puede traer su propia consulta
 * (`/monitores/equidad?metrica=fairness_value`): se conserva y la
 * llegada se compara solo por `pathname`. Heredero de
 * `pages/onboarding/destino.ts`.
 *
 * la ancla `fila` (antes `panel`) lleva a
 * `/alertas?resaltar=<id>`, sin hash: `alertas/index.tsx` resalta la fila y
 * la desplaza a la vista (reutiliza el `?resaltar=` de onboarding/CX-1), pero
 * no abre la hoja, que abre el usuario con un clic. La ancla `configurar`
 * (paso «Dónde se configura el protocolo») no necesita rama propia aquí: cae
 * en el retorno genérico (`/monitores/equidad#configurar`) y es
 * `monitores/index.tsx` quien abre la hoja de configuración al leer ese hash.
 *
 * Es una función pura sobre lo ya cargado (proyecto, reproducción, alertas):
 * el `Provider` decide qué pedir. Un destino sin resolver dice por qué
 * (`falta`), y el panel lo cuenta con el botón para volver al paso que lo crea.
 */

import type { PasoDemo } from "@/api/queries-contenido";
import type { Alert } from "@/api/types";
import type { FaseResumen } from "@/pages/demo/tipos";

import { resumenDeFase } from "./dato";
import { citasDe, esPasoDeAnotacion } from "./pasos";

export { citasDe };

export type FaltaDestino = "proyecto" | "lote" | "alerta";

export interface DestinoResuelto {
  href: string | null;
  ancla: string | null;
  /** Solo la ruta, sin query ni hash: es lo que se compara con `useLocation().pathname`. */
  pathname: string | null;
  falta: FaltaDestino | null;
}

export interface ContextoDestino {
  scenarioKey: string;
  projectId: number | null;
  resultado: FaseResumen[];
  alertas: Alert[];
}

const SIN_DESTINO: DestinoResuelto = { href: null, ancla: null, pathname: null, falta: null };

/**
 * La alerta que el paso narra: la de su `metric_key`, abierta antes que
 * cerrada (la lista viene más reciente primero). Cae a cualquier alerta de
 * equidad si esa métrica no tiene ninguna.
 */
export function mejorAlerta(alertas: Alert[], paso: PasoDemo): Alert | null {
  const metricKey = paso.dato.metric_key;
  // una alerta retirada (lote borrado) no es destino de la demo.
  const vivas = alertas.filter((a) => a.status !== "retirada");
  const deMetrica = metricKey ? vivas.filter((a) => a.metric_key === metricKey) : [];
  return (
    deMetrica.find((a) => a.status !== "cerrada") ??
    deMetrica[0] ??
    vivas.find((a) => a.monitor_type === "fairness") ??
    null
  );
}

export function resolverDestino(paso: PasoDemo | null, ctx: ContextoDestino): DestinoResuelto {
  if (!paso) return SIN_DESTINO;
  const { ruta, ancla } = paso.destino;

  if (paso.tipo === "diapositiva" || ruta === null) {
    return { href: `/demo?paso=${paso.id}`, ancla: null, pathname: "/demo", falta: null };
  }

  const [rutaBase = "", consultaRuta = ""] = ruta.split("?");
  let pathname = rutaBase;
  const params = new URLSearchParams(consultaRuta);

  if (pathname.includes(":batch")) {
    const resumen = resumenDeFase(ctx.resultado, paso);
    if (!resumen) return { ...SIN_DESTINO, falta: "lote" };
    pathname = pathname.replace(":batch", String(resumen.batch_id));
  }

  // en un monitor, el paso apunta a la evaluación de su propio
  // lote. Sin esto, volver a un paso ya reproducido con `?paso=N&run=<id>`
  // enseña la última evaluación del proyecto (la de después de las medidas),
  // no la que narra el paso. Si el paso no tiene fase con lote, se deja como
  // estaba y el monitor sigue abriendo por la última.
  if (pathname.startsWith("/monitores/")) {
    const resumen = resumenDeFase(ctx.resultado, paso);
    if (resumen?.batch_id != null) params.set("lote", String(resumen.batch_id));
  }

  if (pathname.startsWith("/alertas/:id")) {
    const alerta = mejorAlerta(ctx.alertas, paso);
    if (!alerta || alerta.id === null) return { ...SIN_DESTINO, falta: "alerta" };
    pathname = pathname.replace(":id", String(alerta.id));
  } else if (pathname.includes(":id")) {
    if (ctx.projectId === null) return { ...SIN_DESTINO, falta: "proyecto" };
    pathname = pathname.replace(":id", String(ctx.projectId));
  }

  if (esPasoDeAnotacion(paso)) {
    params.set("demo", "anotar");
    params.set("texto", citasDe(paso.hace)[0] ?? "");
  } else if (ancla === "crear-modelo") {
    params.set("demo", "crear");
  } else if (ancla === "subir-datos") {
    params.set("demo", "subir");
    params.set("guion", ctx.scenarioKey);
    params.set("fase", "b1");
  } else if (ancla === "fila") {
    // resalta la fila en vez de abrir la hoja; no hay elemento
    // `id="fila"` al que saltar, así que esta ancla no deja hash (abajo).
    const alerta = mejorAlerta(ctx.alertas, paso);
    if (!alerta || alerta.id === null) return { ...SIN_DESTINO, falta: "alerta" };
    params.set("resaltar", String(alerta.id));
  }

  const anclaSalto = ancla === "fila" ? null : ancla;
  const query = params.size > 0 ? `?${params.toString()}` : "";
  return { href: `${pathname}${query}${anclaSalto ? `#${anclaSalto}` : ""}`, ancla: anclaSalto, pathname, falta: null };
}

/** Cuánto se espera a que el elemento del ancla exista (la ficha de una alerta carga por REST). */
const ESPERA_ANCLA_MS = 4000;
/** Repeticiones del salto una vez visto el elemento: la pantalla sigue creciendo por encima de él. */
const REPETICIONES_MS = [300, 1200, 2500];

/**
 * Desplaza al elemento del ancla en la pantalla destino. Se programa en el
 * clic, antes de navegar: en una SPA el navegador solo intenta el salto al
 * hash en la carga inicial, y la pantalla monta su contenido de forma
 * asíncrona. El temporizador vive fuera del árbol de React, así que sigue en
 * pie aunque cambie la ruta. Espera hasta `ESPERA_ANCLA_MS` a que el
 * elemento exista; al verlo salta, y repite el salto pasados 300, 1200 y 2500 ms
 * porque lo que hay por encima (cabecera, tarjetas de la alerta) aún puede
 * cambiar de altura. Para en cuanto el usuario hace scroll (`wheel` o
 * `touchmove`) para no pelear con él. Desplazamiento instantáneo: respeta
 * `prefers-reduced-motion` sin rama aparte y no se queda a medias en una
 * pestaña en segundo plano. Si el elemento no aparece, se deja de intentar
 * sin ruido.
 */
export function programarScrollAAncla(ancla: string | null): void {
  if (!ancla) return;
  const inicio = Date.now();
  const temporizadores: number[] = [];
  const parar = () => {
    for (const t of temporizadores) {
      window.clearTimeout(t);
      window.clearInterval(t);
    }
    temporizadores.length = 0;
    window.removeEventListener("wheel", parar);
    window.removeEventListener("touchmove", parar);
  };
  const saltar = () => document.getElementById(ancla)?.scrollIntoView({ behavior: "auto", block: "start" });
  window.addEventListener("wheel", parar, { passive: true });
  window.addEventListener("touchmove", parar, { passive: true });
  const intervalo = window.setInterval(() => {
    if (!document.getElementById(ancla)) {
      if (Date.now() - inicio >= ESPERA_ANCLA_MS) parar();
      return;
    }
    window.clearInterval(intervalo);
    saltar();
    for (const ms of REPETICIONES_MS) temporizadores.push(window.setTimeout(saltar, ms));
    temporizadores.push(window.setTimeout(parar, Math.max(...REPETICIONES_MS) + 50));
  }, 150);
  temporizadores.push(intervalo);
}
