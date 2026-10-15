/**
 * `/demo`: sin parámetros, la presentación
 * (`./presentacion`) y, si hay una demo guiada empezada, encima
 * la tarjeta «Demo en curso» con «Continuar» y «Reiniciar». `?paso=N` activa
 * la demo guiada en ese paso (`?run=ID` adopta además una reproducción ya
 * existente: sirve para las capturas y para verificar sobre `demo_local.py`);
 * los pasos sin pantalla (0 y «Fin del caso») se pintan aquí con `Escena`.
 * `#laboratorio` pinta el laboratorio de la reproducción activa (paso 27).
 *
 * El reproductor por fases vive dentro de la demo guiada: el
 * progreso, `matches_expected` (en el dato de cada paso) y el reinicio están
 * en el panel acoplado.
 */

import { useEffect, useRef } from "react";
import { Link, useLocation } from "react-router";

import { useGuiones, useReproduccion } from "@/api/queries-demo";
import { Button } from "@/components/ui/button";
import { BotonModoPresentacion, BotonReiniciarDemo, EmptyState, PageHeader, useDemoGuiada } from "@/components/vigia";
import { useTitulo } from "@/hooks/useTitulo";

import { Diapositiva } from "./Diapositiva";
import { PanelLaboratorio } from "./laboratorio";
import { Presentacion } from "./presentacion";
import { ETIQUETA_ESTADO_RUN } from "./tipos";

function numeroONulo(v: string | null): number | null {
  if (v === null || v === "") return null;
  const n = Number(v);
  return Number.isInteger(n) && n >= 0 ? n : null;
}

export default function Demo() {
  useTitulo("Demo");
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const pasoUrl = numeroONulo(params.get("paso"));
  const runUrl = numeroONulo(params.get("run"));
  const enLaboratorio = location.hash === "#laboratorio";

  const demo = useDemoGuiada();
  const { activa, paso, runId, projectId, contenido, empezar } = demo;
  const runAdoptarQ = useReproduccion(runUrl);
  const runAdoptar = runAdoptarQ.data ?? null;

  // Activación por URL, una vez por URL. Efecto y no ajuste en el render
  // porque `empezar` navega al destino del paso. `aplicada` evita que un
  // cambio de estado posterior (pulsar «Siguiente» mientras la ruta aún es
  // `/demo?paso=0`: React Router aplica la navegación como transición, después
  // del estado) vuelva a activar el paso de la URL y deshaga el avance.
  const claveUrl = pasoUrl === null ? null : `${pasoUrl}|${runUrl ?? ""}|${runUrl !== null ? (runAdoptar?.id ?? "?") : ""}`;
  const aplicada = useRef<string | null>(null);
  useEffect(() => {
    if (claveUrl === null || pasoUrl === null || aplicada.current === claveUrl) return;
    if (runUrl !== null && !runAdoptar) return;
    aplicada.current = claveUrl;
    if (activa && paso === pasoUrl && (runUrl === null || runId === runUrl)) return;
    empezar(pasoUrl, runUrl, runAdoptar?.project_id ?? null);
  }, [claveUrl, pasoUrl, runUrl, runAdoptar, activa, paso, runId, empezar]);

  const run = runUrl !== null ? runAdoptar : demo.run;
  const pasoDiapositiva = pasoUrl !== null ? (contenido?.pasos[pasoUrl] ?? null) : null;

  if (enLaboratorio) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          titulo="Laboratorio"
          descripcion="Mueve la población y el sesgo del lote de casos nuevos y mira qué pasa con los monitores."
          acciones={<BotonModoPresentacion />}
        />
        {run ? (
          <PanelLaboratorio run={run} />
        ) : (
          <EmptyState
            titulo="No hay una demo en curso"
            descripcion="El laboratorio ensaya sobre el modelo de la demo guiada: empieza la demo y sube la línea base para tenerlo."
            accion={
              <Button asChild>
                <Link to="/demo?paso=0">Empezar la demo</Link>
              </Button>
            }
          />
        )}
      </div>
    );
  }

  if (pasoDiapositiva && pasoDiapositiva.tipo === "diapositiva") {
    return <Diapositiva paso={pasoDiapositiva} />;
  }

  const hayDemo = activa || runId !== null || projectId !== null || paso > 0;
  return (
    <div className="flex flex-col gap-6">
      {hayDemo ? <TarjetaDemoEnCurso /> : null}
      <Presentacion />
    </div>
  );
}

/** «Demo en curso: paso N de 29» con «Continuar» y «Reiniciar». */
function TarjetaDemoEnCurso() {
  const { paso, pasos, run, empezar, completado } = useDemoGuiada();
  const guionesQ = useGuiones();
  const titulo = guionesQ.data?.items.find((s) => s.key === run?.scenario_key)?.title;
  const estadoRun = run ? (ETIQUETA_ESTADO_RUN[run.status] ?? run.status) : null;

  return (
    <div
      className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-border bg-card px-4 py-3 text-sm shadow-sm"
      data-demo-en-curso="true"
    >
      <span className="inline-block size-2 rounded-full" style={{ background: "var(--chip-active)" }} aria-hidden="true" />
      <span className="font-semibold">
        {/* Numeración de 1 a 29 (`paso` cuenta desde 0). */}
        {completado ? "Demo completada" : "Demo en curso"}: paso {paso + 1} de {pasos.length}
      </span>
      {titulo ? <span className="text-muted-foreground">{titulo}</span> : null}
      {estadoRun ? <span className="text-muted-foreground">{estadoRun}</span> : null}
      <div className="ml-auto flex items-center gap-2">
        <Button type="button" size="sm" onClick={() => empezar(paso)}>
          Continuar
        </Button>
        <BotonReiniciarDemo />
      </div>
    </div>
  );
}
