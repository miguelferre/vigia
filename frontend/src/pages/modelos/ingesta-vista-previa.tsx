/**
 * Vista previa del paso «Ingerir»: las primeras filas de
 * la respuesta de la subida como tabla con cabeceras, no como visor JSON. Es
 * la misma forma que la del alta (`alta-vista-previa.tsx`), sin papeles de
 * columna porque el mapeo ya se hizo en el paso anterior.
 */

import { TITULO_VISTA_PREVIA_INGESTA } from "./subida-textos";

const FILAS_VISIBLES = 5;

type Fila = Record<string, unknown>;

function comoFilas(preview: unknown): Fila[] {
  if (!Array.isArray(preview)) return [];
  return preview.filter((f): f is Fila => !!f && typeof f === "object" && !Array.isArray(f));
}

function comoTexto(valor: unknown): string {
  if (valor === null || valor === undefined) return "";
  if (typeof valor === "object") return JSON.stringify(valor);
  return String(valor);
}

export function VistaPreviaIngesta({ preview }: { preview: unknown }) {
  const filas = comoFilas(preview);
  if (filas.length === 0) return null;
  const columnas = [...new Set(filas.flatMap((f) => Object.keys(f)))];
  const visibles = filas.slice(0, FILAS_VISIBLES);
  return (
    <div className="flex min-w-0 max-w-full flex-col gap-1.5" data-testid="ingesta-vista-previa">
      <p className="text-sm font-medium">{TITULO_VISTA_PREVIA_INGESTA(visibles.length, filas.length)}</p>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full border-collapse text-xs whitespace-nowrap">
          <thead>
            <tr className="bg-muted/50 text-left">
              {columnas.map((c) => (
                <th key={c} scope="col" className="px-2 py-1.5 font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibles.map((fila, i) => (
              <tr key={i} className="border-t border-border">
                {columnas.map((c) => (
                  <td key={c} className="px-2 py-1 tabular-nums">
                    {comoTexto(fila[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
