/**
 * La acción propia del paso en el panel de la demo guiada:
 * la diapositiva inicial ofrece «Empezar»; «Fin del caso» solo
 * «Ir al laboratorio» (el paso opcional «Tras las medidas» salió del guion); los pasos que cargan un lote lanzan `next` con su progreso, y el
 * resto llevan a su pantalla (el de la alerta solo navega: «Hacer el triaje»
 * se pulsa en el panel de la alerta). Las etiquetas que el
 * guion nombra entre « y » salen de `hace` (`citasDe`); las de navegación son
 * de la interfaz, por ancla o ruta. Un destino sin resolver dice qué falta y
 * a qué paso volver, en vez de un botón muerto.
 */

import { Link } from "react-router";

import type { PasoDemo } from "@/api/queries-contenido";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

import { useDemoGuiada } from "./contexto";
import { programarScrollAAncla, type FaltaDestino } from "./destino";
import { citasDe, esPasoDeAnotacion, esPasoDeCarga } from "./pasos";

const ETIQUETA_POR_ANCLA: Readonly<Record<string, string>> = {
  "crear-modelo": "Ir a crear el modelo",
  "subir-datos": "Ir a subir la línea base",
  monitores: "Ver los monitores del modelo",
  laboratorio: "Abrir el laboratorio",
  // la ancla `fila` reemplaza a `panel` (ya no la usa
  // ningún paso del guion, comprobado por grep en el contenido).
  fila: "Ver la alerta en la lista",
  configurar: "Abrir la configuración del monitor",
  protocolo: "Abrir el protocolo",
  calculo: "Ver cómo se ha calculado",
};

const ETIQUETA_POR_RUTA: ReadonlyArray<[prefijo: string, etiqueta: string]> = [
  ["/monitores/equidad", "Abrir el monitor de equidad"],
  ["/monitores/calidad", "Abrir el monitor de calidad"],
  ["/monitores/deriva", "Abrir el monitor de deriva"],
  ["/cuadro", "Abrir el cuadro de mando"],
  ["/diario", "Abrir el diario"],
  ["/alertas", "Abrir las alertas"],
  ["/explicabilidad", "Abrir Explicabilidad"],
  ["/datos", "Abrir el lote"],
  ["/modelos", "Abrir el modelo"],
];

function etiquetaNavegacion(paso: PasoDemo): string {
  const { ruta, ancla } = paso.destino;
  if (esPasoDeAnotacion(paso)) return "Anotar en el diario";
  if (ancla && ETIQUETA_POR_ANCLA[ancla]) return ETIQUETA_POR_ANCLA[ancla];
  const porRuta = ETIQUETA_POR_RUTA.find(([prefijo]) => ruta?.startsWith(prefijo));
  return porRuta?.[1] ?? "Ir a la pantalla";
}

const TEXTO_FALTA: Readonly<Record<FaltaDestino, string>> = {
  proyecto: "Antes hay que crear el modelo.",
  lote: "Antes hay que cargar el lote de este paso.",
  alerta: "Antes hay que cargar el lote que dispara la alerta.",
};

export function AccionPaso() {
  const demo = useDemoGuiada();
  const paso = demo.pasoActual;
  if (!paso) return null;
  const citas = citasDe(paso.hace);

  if (paso.tipo === "diapositiva") {
    if (paso.id === 0) {
      return (
        <Button type="button" size="sm" onClick={() => demo.ir(1)}>
          {citas[0] ?? "Empezar"}
        </Button>
      );
    }
    // «Fin del caso»: el laboratorio es el siguiente paso.
    return (
      <Button type="button" size="sm" onClick={demo.siguiente}>
        {citas[0] ?? "Ir al laboratorio"}
      </Button>
    );
  }

  if (esPasoDeCarga(demo.pasos, paso.id)) {
    const { trabajo } = demo;
    if (demo.runId === null) {
      return <Falta texto={TEXTO_FALTA.lote} volverA={pasoDeCargaPrevio(demo.pasos, paso.id, true)} ir={demo.ir} />;
    }
    if (trabajo.enCurso && trabajo.pasoLanzado === paso.id) {
      return (
        <div className="flex w-full flex-col gap-1.5" data-trabajo="en-curso">
          <Progress value={trabajo.progreso * 100} />
          <span className="text-xs text-muted-foreground">{trabajo.mensaje || "Cargando el lote…"}</span>
        </div>
      );
    }
    if (demo.resultado.length >= paso.fase_minima) {
      return <span className="text-xs text-muted-foreground">Lote cargado y evaluado.</span>;
    }
    return (
      <Button type="button" size="sm" onClick={() => void trabajo.lanzar(paso.id)} disabled={trabajo.enCurso}>
        {citas[0] ?? "Cargar el lote"}
      </Button>
    );
  }

  const { destino } = demo;
  if (destino.falta !== null) {
    return (
      <Falta
        texto={TEXTO_FALTA[destino.falta]}
        volverA={destino.falta === "proyecto" ? 1 : pasoDeCargaPrevio(demo.pasos, paso.id, false)}
        ir={demo.ir}
      />
    );
  }
  if (destino.href === null) return null;
  return (
    <Button asChild size="sm" variant="outline" onClick={() => programarScrollAAncla(destino.ancla)}>
      <Link to={destino.href}>{etiquetaNavegacion(paso)}</Link>
    </Button>
  );
}

/**
 * El paso que crea lo que falta: el de carga con la misma `fase_minima`
 * (o el de subir la línea base, ancla `subir-datos`, cuando falta la
 * reproducción entera).
 */
function pasoDeCargaPrevio(pasos: PasoDemo[], n: number, lineaBase: boolean): number {
  if (lineaBase) return pasos.find((p) => p.destino.ancla === "subir-datos")?.id ?? 2;
  const objetivo = pasos[n]?.fase_minima ?? 0;
  for (let i = n - 1; i >= 0; i -= 1) {
    if (esPasoDeCarga(pasos, i) && pasos[i]!.fase_minima === objetivo) return i;
  }
  return Math.max(0, n - 1);
}

function Falta({ texto, volverA, ir }: { texto: string; volverA: number; ir: (n: number) => void }) {
  return (
    <div className="flex flex-col gap-2" data-falta="true">
      <p className="text-xs" style={{ color: "var(--state-warn)" }}>
        {texto}
      </p>
      <Button type="button" size="sm" variant="outline" onClick={() => ir(volverA)}>
        Ir al paso {volverA}
      </Button>
    </div>
  );
}
