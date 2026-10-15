/**
 * Explicabilidad de un modelo multiclase: qué se explica y las
 * `k` probabilidades de una fila. `ClaseExplicadaPanel` va bajo la cabecera de
 * `detalle.tsx`; `SelectorClaseExplicacion` va en el lanzador (`lanzar.tsx`).
 *
 * La global explica por defecto la probabilidad del conjunto favorable
 * y deja elegir una clase; la local explica por defecto la clase que predijo
 * el modelo para esa fila y trae las `k` probabilidades en el orden de
 * las clases del proyecto.
 */

import type { JsonObject } from "@/api/types";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { claveClase } from "@/lib/tipo-tarea";

/** Valor interno de «lo que explica el backend si no se pide nada» (un `SelectItem` no admite la cadena vacía). */
export const CLASE_POR_DEFECTO = "__defecto__";

const PORCENTAJE = new Intl.NumberFormat("es-ES", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });

interface SelectorProps {
  id: string;
  etiqueta: string;
  /** Texto de la opción por defecto: dice qué se explica si no se elige clase. */
  porDefecto: string;
  clases: string[];
  valor: string;
  onChange: (v: string) => void;
  ayuda: string;
}

export function SelectorClaseExplicacion({ id, etiqueta, porDefecto, clases, valor, onChange, ayuda }: SelectorProps) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>{etiqueta}</Label>
      <Select value={valor} onValueChange={onChange}>
        <SelectTrigger id={id} className="w-full sm:w-72" aria-describedby={`${id}-ayuda`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={CLASE_POR_DEFECTO}>{porDefecto}</SelectItem>
          {clases.map((c) => (
            <SelectItem key={c} value={c}>
              {c}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p id={`${id}-ayuda`} className="text-xs text-muted-foreground">
        {ayuda}
      </p>
    </div>
  );
}

function lista(valor: unknown): string[] {
  return Array.isArray(valor) ? valor.map(String) : [];
}

/** Frase de «qué explica» para una explicación global o local de un modelo multiclase. */
export function fraseQueExplica(resultado: JsonObject | null, params: JsonObject | null, local: boolean, favorables: string[]): string {
  const clase = typeof resultado?.clase_explicada === "string" ? resultado.clase_explicada : null;
  if (local) {
    return clase
      ? `Explica la probabilidad de la clase «${clase}».`
      : "Explica la probabilidad de la clase predicha para esta fila.";
  }
  if (params?.objetivo === "favorables") {
    const conjunto = lista(params.clases);
    return `Explica la probabilidad del conjunto favorable (${(conjunto.length > 0 ? conjunto : favorables).join(", ")}).`;
  }
  if (clase) return `Explica la probabilidad de la clase «${clase}».`;
  return `Explica la probabilidad del conjunto favorable (${favorables.join(", ")}).`;
}

interface PanelProps {
  resultado: JsonObject | null;
  params: JsonObject | null;
  local: boolean;
  clases: string[];
  favorables: string[];
}

export function ClaseExplicadaPanel({ resultado, params, local, clases, favorables }: PanelProps) {
  const probs = Array.isArray(resultado?.probabilities)
    ? (resultado.probabilities as unknown[]).filter((p): p is number => typeof p === "number")
    : [];
  const explicada = typeof resultado?.clase_explicada === "string" ? resultado.clase_explicada : null;
  const nombres = clases.length === probs.length ? clases : probs.map((_, i) => `Clase ${i + 1}`);
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-muted/30 p-3" data-testid="clase-explicada">
      <p className="text-sm font-medium">{fraseQueExplica(resultado, params, local, favorables)}</p>
      {local && probs.length > 0 ? (
        <ul className="flex flex-col gap-1.5" aria-label="Probabilidad de cada clase para esta fila">
          {nombres.map((nombre, i) => {
            const p = probs[i];
            const esExplicada = explicada !== null && claveClase(nombre) === claveClase(explicada);
            return (
              <li key={nombre} className="grid grid-cols-[minmax(5rem,10rem)_1fr_4rem] items-center gap-2 text-xs">
                <span className={`[overflow-wrap:anywhere] ${esExplicada ? "font-semibold" : ""}`}>
                  {nombre}
                  {favorables.includes(claveClase(nombre)) ? <span className="text-muted-foreground"> · favorable</span> : null}
                </span>
                <span className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                  <span
                    className="block h-full rounded-full"
                    style={{
                      width: `${Math.round(Math.max(0, Math.min(1, p)) * 100)}%`,
                      background: esExplicada ? "var(--chart-1)" : "var(--line-2)",
                    }}
                  />
                </span>
                <span className="text-right tabular-nums">{PORCENTAJE.format(p)}</span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
