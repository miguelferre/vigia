/**
 * Vista previa del paso «Datos» del alta: las cinco primeras filas del
 * fichero de ejemplo con el papel de cada columna en la cabecera. Sirve para
 * comprobar el reparto antes de crear el modelo; se ve en el navegador, el
 * fichero no se sube.
 */

import { PAPEL, TITULO_VISTA_PREVIA } from "./alta-textos";

const FILAS_VISTA_PREVIA = 5;

interface Props {
  columnas: string[];
  filas: Record<string, string>[];
  /** Papel o papeles de cada columna (`alta-roles.ts::papelesDeColumna`). */
  papeles: Record<string, string[]>;
}

export function VistaPreviaAlta({ columnas, filas, papeles }: Props) {
  const visibles = filas.slice(0, FILAS_VISTA_PREVIA);
  return (
    <div className="flex min-w-0 max-w-full flex-col gap-1.5" data-testid="alta-vista-previa">
      <p className="text-sm font-medium">{TITULO_VISTA_PREVIA(FILAS_VISTA_PREVIA)}</p>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full border-collapse text-xs whitespace-nowrap">
          <thead>
            <tr className="bg-muted/50 text-left align-bottom">
              {columnas.map((c) => {
                const papel = (papeles[c] ?? [PAPEL.sinUsar]).join(" + ");
                return (
                  <th key={c} scope="col" className="px-2 py-1.5 font-normal">
                    <span className="block font-medium">{c}</span>
                    <span
                      className={papel === PAPEL.sinUsar ? "text-muted-foreground" : "text-primary"}
                      data-testid="papel-columna"
                    >
                      {papel}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visibles.map((fila, i) => (
              <tr key={i} className="border-t border-border">
                {columnas.map((c) => (
                  <td key={c} className="px-2 py-1 tabular-nums">
                    {fila[c] ?? ""}
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
