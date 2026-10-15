/**
 * Qué decisión declara quien sube el registro de uso, según el tipo de tarea:
 * `derivacion` pregunta la decisión favorable,
 * `clases` enseña las clases del modelo y `rango` explica que el
 * registro trae cifras en la unidad del modelo. Un `switch` sin
 * `default` abierto: un valor nuevo de `decisionHumana` hace fallar `tsc`.
 * Aparte de `RegistroUso.tsx` por el límite de 9 KB.
 */

import { Link } from "react-router";

import type { ValorFavorable } from "@/api/types";
import { textoRangos, type RangoFavorable } from "@/lib/metrics";
import type { CapacidadesTarea } from "@/lib/tipo-tarea";
import { ClasesRegistro } from "./registro-uso-clases";
import { FavorableRegistro } from "./registro-uso-favorable";
import type { RegistroUsoAyuda } from "./registro-uso-ayuda";

/** El motivo de la API; este es el texto de reserva si aún no ha llegado. */
export const MOTIVO_SIN_RANGO = "la capa humana de regresión necesita un rango favorable";

interface Props {
  decision: CapacidadesTarea["decisionHumana"];
  ayuda: RegistroUsoAyuda | undefined;
  favorable: ValorFavorable | null;
  onElegir: (valor: ValorFavorable) => void;
  clases: string[];
  favorables: string[];
  unidad: string | null;
  rangos: RangoFavorable[];
}

export function DecisionRegistro({ decision, ayuda, favorable, onElegir, clases, favorables, unidad, rangos }: Props) {
  switch (decision) {
    case "derivacion":
      return <FavorableRegistro ayuda={ayuda} favorable={favorable} onElegir={onElegir} />;
    case "clases":
      return <ClasesRegistro clases={clases} favorables={favorables} />;
    case "rango":
      return <CifrasRegistro unidad={unidad} rangos={rangos} />;
    default: {
      const _exhaustivo: never = decision;
      throw new Error(`decisión humana no reconocida: ${String(_exhaustivo)}`);
    }
  }
}

/** Regresión con rango: las tres columnas de decisión llevan cifras. */
function CifrasRegistro({ unidad, rangos }: { unidad: string | null; rangos: RangoFavorable[] }) {
  const rango = textoRangos(rangos, unidad);
  return (
    <div className="flex flex-col gap-1.5" data-testid="registro-uso-cifras">
      <p className="text-sm font-medium">Las decisiones van con cifras{unidad ? `, en ${unidad}` : ""}</p>
      <p className="text-xs text-muted-foreground">
        Las columnas human_decision, model_output y ground_truth llevan un número con punto decimal y sin la unidad.
        No valen refer ni no-refer. {rango ? `Una cifra cuenta como favorable si cae ${rango}. ` : ""}Vigía calcula
        solo si cada cifra cae dentro o fuera del rango.
      </p>
      <p className="text-xs text-muted-foreground">
        Un cambio del profesional que no cruza el corte del rango no cuenta como override: si la cifra del modelo y la
        de la persona caen las dos dentro del rango, o las dos fuera, la decisión sigue igual.
      </p>
    </div>
  );
}

/** Sin rango favorable la capa humana no existe; se dice por qué y qué hacer. */
export function SinRangoCapaHumana({ motivo }: { motivo?: string | null }) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-muted/40 p-3" data-testid="capa-humana-sin-rango">
      <p className="text-sm font-medium">Este modelo no tiene capa humana</p>
      <p className="text-sm text-muted-foreground">
        {`${(motivo ?? MOTIVO_SIN_RANGO).replace(/^./, (c) => c.toUpperCase()).replace(/\.$/, "")}. `}
        El rango favorable se fija en el alta o en la plantilla antes de congelar la línea base. Qué hacer: si la
        línea base ya está congelada, crea un modelo nuevo con rango favorable.
      </p>
      <Link to="/modelos?alta=1" className="w-fit text-sm text-primary underline underline-offset-2">
        Crear un modelo nuevo con rango favorable
      </Link>
    </div>
  );
}

/** Frase del diálogo de subida: qué decisiones lleva el fichero. */
export function descripcionSubida(
  decision: CapacidadesTarea["decisionHumana"] | undefined,
  nombre: string | undefined,
  version: string,
  favorable: ValorFavorable | null,
): string {
  const base = `Sube ${nombre ?? "el CSV"} a la versión ${version}`;
  switch (decision) {
    case undefined:
      return `${base}.`;
    case "derivacion":
      return `${base}, con «${favorable ?? "?"}» como decisión favorable.`;
    case "clases":
      return `${base}, con nombres de clase en las decisiones.`;
    case "rango":
      return `${base}, con cifras en las decisiones.`;
    default: {
      const _exhaustivo: never = decision;
      throw new Error(`decisión humana no reconocida: ${String(_exhaustivo)}`);
    }
  }
}
