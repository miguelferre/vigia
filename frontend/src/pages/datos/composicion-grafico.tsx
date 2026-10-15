/**
 * Piezas del gráfico de composición de `/datos/:batch` (barra apilada, etiqueta de favorables y tooltip),
 * partidas de `composicion.tsx` por tamaño (tres modos según el resultado bueno).
 */

import type { LabelProps } from "recharts";

import { formatoPorcentaje } from "@/components/vigia/calculo-datos";
import { formatoNumero, textoRangos, type RangoFavorable } from "@/lib/metrics";

import type { FilaComposicion, ModoComposicion } from "./composicion-modos";

/** Recuento de favorables sobre la barra: siempre el segmento superior. */
export function EtiquetaFavorable(props: LabelProps) {
  const valor = props.value;
  if (valor === null || valor === undefined || valor === "") return null;
  const x = Number(props.x);
  const y = Number(props.y);
  const ancho = Number(props.width);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(ancho)) return null;
  return (
    <text x={x + ancho / 2} y={y - 6} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--foreground)">
      {formatoNumero(Number(valor), 0)}
    </text>
  );
}

interface TooltipComposicionProps {
  active?: boolean;
  payload?: { payload?: FilaComposicion }[];
  modo: ModoComposicion;
}

/** Mismo cuadro opaco que `ChartTooltipContent`, con la lectura compuesta de predicción frente a etiqueta. */
export function TooltipComposicion({ active, payload, modo }: TooltipComposicionProps) {
  const fila = payload?.[0]?.payload;
  if (!active || !fila) return null;
  if (modo === "sin_rango") {
    return (
      <div
        className="flex min-w-48 flex-col gap-1 rounded-md p-2.5 text-xs"
        style={{ background: "var(--card)", color: "var(--card-foreground)", boxShadow: "var(--elevation-pop)" }}
      >
        <p className="font-semibold">{fila.grupo}</p>
        <p>Registros: {formatoNumero(fila.n, 0)}</p>
      </div>
    );
  }
  return (
    <div
      className="flex min-w-48 flex-col gap-1 rounded-md p-2.5 text-xs"
      style={{ background: "var(--card)", color: "var(--card-foreground)", boxShadow: "var(--elevation-pop)" }}
    >
      <p className="font-semibold">{fila.grupo}</p>
      <p>
        {modo === "rango" ? "Dentro del rango" : "Favorables"}: {formatoNumero(fila.favorable, 0)} ({formatoPorcentaje(fila.predRate)}) · Registros:{" "}
        {formatoNumero(fila.n, 0)}
      </p>
    </div>
  );
}

export interface TextoFavorablesProps {
  modo: ModoComposicion;
  /** Multiclase: el favorable es un conjunto de clases (`caps.favorables === "conjunto"`). */
  conjunto: boolean;
  favorables: string[];
  rangos: readonly RangoFavorable[];
  unidad: string | null;
  /** `BatchComposition.motivo`: por qué no hay favorables. */
  motivo: string | null | undefined;
}

/** Qué cuenta como favorable en la composición: el rango, el conjunto de clases o el motivo de que no haya. */
export function TextoFavorables({ modo, conjunto, favorables, rangos, unidad, motivo }: TextoFavorablesProps) {
  if (modo === "rango") {
    return (
      <p className="text-sm text-muted-foreground" data-testid="composicion-rango">
        Cuenta como favorable: {textoRangos(rangos, unidad)}. «Dentro del rango» cuenta las filas cuya predicción cae en
        ese rango; el resto va en «Resto».
      </p>
    );
  }
  if (modo === "sin_rango") {
    return (
      <p className="text-sm text-muted-foreground" data-testid="composicion-sin-rango">
        <span className="font-semibold text-foreground">Este modelo no tiene un rango favorable</span> (
        {motivo ?? "sin rango favorable: solo el error por grupo"}), así que la composición solo cuenta los registros de
        cada grupo. Para ver cuántos caen dentro de un rango, defínelo en la plantilla del modelo.
      </p>
    );
  }
  if (!conjunto) return null;
  return (
    <p className="text-sm text-muted-foreground" data-testid="composicion-favorables">
      {favorables.length > 0
        ? `Clases favorables: ${favorables.join(", ")}. «Favorables» cuenta las filas cuya clase predicha está en ese conjunto; el resto de clases va en «Resto».`
        : "Este modelo no tiene clases favorables marcadas: «Favorables» no cuenta ninguna fila."}
    </p>
  );
}
