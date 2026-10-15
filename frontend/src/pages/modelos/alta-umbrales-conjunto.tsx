/**
 * Nota única del paso «Umbrales» del alta: con dos o más
 * filas con origen propio (fabricante, responsable o política), una sola nota
 * vale para todas y se copia a cada fila al guardar (la API guarda la nota en
 * cada umbral). Con una sola fila, la nota sigue en su fila.
 */

import { Input } from "@/components/ui/input";
import type { Ediciones } from "./alta-umbrales-guardar";
import type { EdicionUmbral } from "./alta-umbrales-fila";

/** Una fila lleva nota propia si su origen no es la propuesta ni el valor actual. */
export function pideNota(e: Pick<EdicionUmbral, "origen">): boolean {
  return e.origen !== "linea_base" && e.origen !== "fabrica";
}

export function filasConNota(ediciones: Ediciones): number {
  return Object.values(ediciones).filter(pideNota).length;
}

/** Con dos o más filas que piden nota, todas toman la del conjunto. */
export function conNotaDelConjunto(ediciones: Ediciones, nota: string): Ediciones {
  if (filasConNota(ediciones) < 2) return ediciones;
  return Object.fromEntries(Object.entries(ediciones).map(([k, e]) => [k, pideNota(e) ? { ...e, nota } : e]));
}

export function NotaConjuntoUmbrales({
  cambiadas,
  nota,
  onCambiar,
}: {
  cambiadas: number;
  nota: string;
  onCambiar: (nota: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5 rounded-md bg-muted/40 p-3" data-testid="nota-umbrales-conjunto">
      <p className="text-sm text-muted-foreground">
        Has cambiado el origen de {cambiadas} umbrales. Una sola nota vale para todos y queda en el diario.
      </p>
      <Input
        placeholder="Nota para todos (obligatoria)"
        aria-label="Nota de los umbrales cambiados"
        value={nota}
        onChange={(e) => onCambiar(e.target.value)}
      />
    </div>
  );
}
