/**
 * Selector «Todas · <clase> · <clase>…» de la tarjeta de confianza:
 * pestañas de `ui/tabs.tsx` (accesibles y con teclado de
 * fábrica), extraído de `histograma-confianza.tsx` para no pasar de los 9 KB
 * por fichero. Sin contenido propio: el contenido lo sigue pintando
 * `HistogramaBaseLote` en el componente que lo monta, con las series de la
 * selección.
 *
 * Las opciones llegan ya construidas (`opciones`): en binario las
 * dos de siempre («Derivar»/«No derivar» o «Clase 1 (favorable)»/«Clase 0»);
 * en multiclase, una por clase. Con `CLASES_PARA_SELECT` clases o más, un
 * `Select`: las pestañas no caben con nombres largos.
 */

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CLASES_PARA_SELECT, type OpcionClase, type SeleccionClase } from "./confianza-por-clase";

export interface SelectorClaseConfianzaProps {
  seleccion: SeleccionClase;
  onSeleccion: (seleccion: SeleccionClase) => void;
  /** Una opción por clase, sin «Todas» (el selector la añade). */
  opciones: OpcionClase[];
}

export function SelectorClaseConfianza({ seleccion, onSeleccion, opciones }: SelectorClaseConfianzaProps) {
  if (opciones.length >= CLASES_PARA_SELECT) {
    return (
      <div className="flex max-w-full items-center gap-2">
        <span className="text-xs text-muted-foreground">Clase predicha</span>
        <Select value={seleccion} onValueChange={onSeleccion}>
          <SelectTrigger size="sm" className="min-w-0 max-w-full flex-1 sm:max-w-sm" aria-label="Clase predicha">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="max-h-80">
            <SelectItem value="todas">Todas</SelectItem>
            {opciones.map((o) => (
              <SelectItem key={o.valor} value={o.valor}>
                {o.etiqueta}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  }
  return (
    <Tabs value={seleccion} onValueChange={(v) => onSeleccion(v)}>
      <TabsList className="h-7">
        <TabsTrigger value="todas" className="px-2.5 text-xs">
          Todas
        </TabsTrigger>
        {opciones.map((o) => (
          <TabsTrigger key={o.valor} value={o.valor} className="px-2.5 text-xs">
            {o.etiqueta}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}

export default SelectorClaseConfianza;
