/** Las probabilidades de todas las clases de una fila, plegadas para no ensanchar la tabla de registros. */

import { formatoNumero } from "@/lib/metrics";

export function ProbabilidadesClases({ probs, clases }: { probs: number[] | null | undefined; clases: string[] }) {
  if (!probs || probs.length === 0) return <span>—</span>;
  return (
    <details className="text-xs">
      <summary className="cursor-pointer select-none">Ver las {probs.length} clases</summary>
      <ul className="mt-1 flex flex-col gap-0.5">
        {probs.map((p, i) => (
          <li key={i} className="flex justify-between gap-3 tabular-nums">
            <span>{clases[i] ?? `Clase ${i + 1}`}</span>
            <span>{formatoNumero(p, 3)}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
