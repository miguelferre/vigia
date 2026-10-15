/**
 * Visor JSON plegable para `result_json`, `config_snapshot` y afines.
 *
 * Nivel a nivel: los objetos y listas empiezan cerrados por debajo de
 * `abiertoHasta`. Sin dependencias nuevas.
 */

import { useState } from "react";
import { ChevronDownIcon, ChevronRightIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import type { JsonValue } from "@/api/types";

export interface JsonViewProps {
  valor: unknown;
  /** Profundidad hasta la que arranca desplegado (0 = solo la raíz). */
  abiertoHasta?: number;
  className?: string;
}

export function JsonView({ valor, abiertoHasta = 1, className }: JsonViewProps) {
  return (
    <div
      className={cn(
        "overflow-x-auto rounded-md border border-border bg-muted/40 p-3 font-mono text-xs leading-relaxed",
        className,
      )}
    >
      <Nodo nombre={null} valor={valor as JsonValue} nivel={0} abiertoHasta={abiertoHasta} />
    </div>
  );
}

interface NodoProps {
  nombre: string | null;
  valor: JsonValue;
  nivel: number;
  abiertoHasta: number;
}

function Nodo({ nombre, valor, nivel, abiertoHasta }: NodoProps) {
  const compuesto = valor !== null && typeof valor === "object";
  const [abierto, setAbierto] = useState(nivel < abiertoHasta);

  if (!compuesto) {
    return (
      <div style={{ paddingLeft: nivel * 12 }}>
        {nombre !== null ? <span className="text-muted-foreground">{nombre}: </span> : null}
        <Escalar valor={valor} />
      </div>
    );
  }

  const entradas: [string, JsonValue][] = Array.isArray(valor)
    ? valor.map((v, i) => [String(i), v])
    : Object.entries(valor);
  const cierre = Array.isArray(valor) ? "[ ]" : "{ }";
  const resumen = Array.isArray(valor)
    ? `${entradas.length} elemento${entradas.length === 1 ? "" : "s"}`
    : `${entradas.length} clave${entradas.length === 1 ? "" : "s"}`;

  return (
    <div style={{ paddingLeft: nivel * 12 }}>
      <button
        type="button"
        onClick={() => setAbierto((a) => !a)}
        className="inline-flex items-center gap-1 rounded hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        aria-expanded={abierto}
      >
        {abierto ? (
          <ChevronDownIcon className="size-3" aria-hidden="true" />
        ) : (
          <ChevronRightIcon className="size-3" aria-hidden="true" />
        )}
        {nombre !== null ? <span className="text-muted-foreground">{nombre}</span> : null}
        <span className="text-muted-foreground">
          {cierre} {resumen}
        </span>
      </button>
      {abierto
        ? entradas.map(([clave, hijo]) => (
            <Nodo
              key={clave}
              nombre={clave}
              valor={hijo}
              nivel={nivel + 1}
              abiertoHasta={abiertoHasta}
            />
          ))
        : null}
    </div>
  );
}

function Escalar({ valor }: { valor: JsonValue }) {
  // `null` va en un elemento `code`, no como texto suelto: es un
  // valor JSON, no una palabra de la interfaz (y el visor de texto de las
  // pruebas lo distingue así).
  if (valor === null) return <code className="text-muted-foreground">null</code>;
  if (typeof valor === "string") return <span>&quot;{valor}&quot;</span>;
  return <span className="tabular-nums">{String(valor)}</span>;
}
