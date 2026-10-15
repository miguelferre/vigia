/**
 * Cabecera de ventana de una evaluación: tipo
 * de ventana, `n`, lotes y versión, con aviso cuando `complete` es falso.
 *
 * `window` no tiene una forma única: `Evaluation.window` es `dict[str, Any]`
 * en el backend (`app/schemas/respuestas_evaluaciones.py`), porque el
 * monitor `cross` guarda una ventana mucho más simple
 * (`{"kind": "acumulado_version", "model_version_id": 1}`, sin `n` ni
 * `batches` ni `complete`) que la de `fairness`/`quality`/`drift`
 * (`WindowInfo` de `core/schema.py`: `kind, n, requested_n, start_seq,
 * end_seq, batches, model_version, complete, motivo, interval_windows`).
 * Cada campo se enseña solo si llega; ninguno se pinta como "null" o
 * "undefined".
 */

import { AlertTriangleIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useGlosario } from "@/api/queries-contenido";
import { cn } from "@/lib/utils";

import { InfoTooltip } from "./InfoTooltip";

/** Forma laxa de `window`: superconjunto de los cuatro `kind` que produce el motor. */
export interface VentanaInfo {
  kind?: string | null;
  n?: number | null;
  requested_n?: number | null;
  batches?: number[] | null;
  model_version?: string | null;
  model_version_id?: number | null;
  complete?: boolean | null;
  motivo?: string | null;
}

export interface CabeceraVentanaProps {
  window: VentanaInfo | Record<string, unknown> | null | undefined;
  /**
   * método del intervalo de la versión con la que se
   * calculó la equidad. `"lote"` es el intervalo de Katz/Newcombe sobre el
   * lote completo; `"ventanas"` es la ventana deslizante. `null`
   * fuera del monitor de equidad.
   */
  intervalMethod?: "ventanas" | "lote" | null;
  /**
   * ventana de la etiqueta (aparte de la de predicción) en el monitor
   * de equidad. Con etiqueta tardía (midas-michigan) puede acumular varios
   * lotes hasta reunir la muestra mínima (`kind === "acumulado"`).
   */
  labelWindow?: VentanaInfo | Record<string, unknown> | null;
  className?: string;
}

const ETIQUETA_METODO_INTERVALO: Record<"ventanas" | "lote", string> = {
  ventanas: "Ventanas móviles",
  lote: "Lote completo",
};

const AYUDA_METODO_INTERVALO: Record<"ventanas" | "lote", string> = {
  lote: "El intervalo de confianza de la equidad se calcula sobre el lote completo (Katz o Newcombe), sin ventana deslizante.",
  ventanas: "El intervalo de confianza de la equidad se calcula sobre una ventana deslizante de los últimos lotes.",
};

const AYUDA_ETIQUETAS_ACUMULADAS =
  "El lote evaluado no reunía etiquetas suficientes por sí solo: la ventana de etiquetas suma lotes anteriores hasta llegar a la muestra mínima.";

const ETIQUETA_KIND: Record<string, string> = {
  ultimos_n: "Últimos N",
  // "Lote completo" y no "Lote" a secas: al lado va el dato "Lote 8", que es
  // el identificador, y dos "Lote" seguidos con sentidos distintos confunden.
  batch: "Lote completo",
  acumulado: "Acumulado",
  baseline_vs_batch: "Línea base frente a lote",
  acumulado_version: "Acumulado por versión",
};

function etiquetaKind(kind: string | null | undefined): string {
  if (!kind) return "Ventana";
  return ETIQUETA_KIND[kind] ?? kind;
}

function Dato({
  etiqueta,
  valor,
  ayuda,
}: {
  etiqueta: string;
  valor: string;
  /** Ayuda contextual del glosario: título y texto del ⓘ, si hay entrada. */
  ayuda?: { titulo: string; texto: string };
}) {
  return (
    <span className="inline-flex items-baseline gap-1 text-xs">
      <span className="text-muted-foreground">{etiqueta}</span>
      <span className="font-semibold tabular-nums">{valor}</span>
      {ayuda ? <InfoTooltip titulo={ayuda.titulo} queMide={ayuda.texto} className="self-center" /> : null}
    </span>
  );
}

const FRASE_VERSION = "Versión del modelo activa cuando se calculó esta evaluación.";

export function CabeceraVentana({ window, intervalMethod, labelWindow, className }: CabeceraVentanaProps) {
  // El hook va antes del `return` condicional (regla de hooks): con
  // `window` vacío la consulta igualmente se resuelve del caché, ya
  // caliente por `FraseAperturaMonitor`/`GlosarioSheet`.
  const glosarioQ = useGlosario();
  const glosario = glosarioQ.data;
  const ayudaVentana = glosario?.ventana ? { titulo: "Ventana", texto: glosario.ventana.definicion } : undefined;
  const ayudaMuestraMinima = glosario?.muestra_minima
    ? { titulo: "Muestra mínima", texto: glosario.muestra_minima.definicion }
    : undefined;
  const ayudaLote = glosario?.lote ? { titulo: "Lote", texto: glosario.lote.definicion } : undefined;

  if (!window || typeof window !== "object") return null;
  const w = window as VentanaInfo;

  const n = typeof w.n === "number" ? w.n : null;
  const requestedN = typeof w.requested_n === "number" ? w.requested_n : null;
  const lotes = Array.isArray(w.batches) && w.batches.length > 0 ? w.batches : null;
  const version = w.model_version ?? (typeof w.model_version_id === "number" ? `id ${w.model_version_id}` : null);
  // `complete` por defecto es true en el backend (`WindowInfo.complete = True`);
  // cuando la ventana ni siquiera trae el campo (caso `acumulado_version`), no
  // hay aviso que mostrar porque no se ha declarado incompleta.
  const incompleta = w.complete === false;

  // la ventana de etiquetas acumula lotes anteriores cuando el lote
  // evaluado no reúne etiquetas suficientes por sí solo (etiqueta tardía,
  // midas-michigan). `batches` trae los lotes incluidos; el más antiguo es
  // desde donde se acumula.
  const lw = labelWindow && typeof labelWindow === "object" ? (labelWindow as VentanaInfo) : null;
  const loteInicioEtiquetas =
    lw?.kind === "acumulado" && Array.isArray(lw.batches) && lw.batches.length > 0 ? Math.min(...lw.batches) : null;

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <Badge variant="outline">{etiquetaKind(w.kind)}</Badge>
        {intervalMethod ? (
          <Dato
            etiqueta="Método del intervalo"
            valor={ETIQUETA_METODO_INTERVALO[intervalMethod]}
            ayuda={{ titulo: "Método del intervalo", texto: AYUDA_METODO_INTERVALO[intervalMethod] }}
          />
        ) : null}
        {loteInicioEtiquetas !== null ? (
          <Dato
            etiqueta="Etiquetas"
            valor={`acumuladas desde el lote ${loteInicioEtiquetas}`}
            ayuda={{ titulo: "Etiquetas acumuladas", texto: AYUDA_ETIQUETAS_ACUMULADAS }}
          />
        ) : null}
        {n !== null ? <Dato etiqueta="Registros" valor={`${n}`} ayuda={ayudaVentana} /> : null}
        {/*
          `requested_n` es la muestra MÍNIMA pedida, no un total: escribirlo
          como "3000 de 100" se lee al revés de lo que significa. Va como dato
          propio, y solo cuando la ventana se queda corta se dice que falta.
        */}
        {requestedN !== null ? (
          <Dato
            etiqueta="Muestra mínima"
            valor={n !== null && n < requestedN ? `${requestedN} (faltan ${requestedN - n})` : `${requestedN}`}
            ayuda={ayudaMuestraMinima}
          />
        ) : null}
        {lotes !== null ? (
          <Dato etiqueta={lotes.length > 1 ? "Lotes" : "Lote"} valor={lotes.join(", ")} ayuda={ayudaLote} />
        ) : null}
        {version !== null ? (
          <Dato etiqueta="Versión" valor={version} ayuda={{ titulo: "Versión", texto: FRASE_VERSION }} />
        ) : null}
      </div>
      {incompleta ? (
        <p
          className="inline-flex items-start gap-1.5 text-xs"
          style={{ color: "var(--state-warn)" }}
        >
          <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>Ventana incompleta{w.motivo ? `: ${w.motivo}` : "."}</span>
        </p>
      ) : null}
    </div>
  );
}

export default CabeceraVentana;
