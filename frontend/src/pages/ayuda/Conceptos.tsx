/** Sección «Conceptos» de `/ayuda`: el glosario agrupado, en tarjetas. */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { GrupoGlosario } from "./agrupar";

export interface ConceptosProps {
  grupos: GrupoGlosario[];
  cargando: boolean;
}

export function Conceptos({ grupos, cargando }: ConceptosProps) {
  if (cargando) {
    return <p className="text-sm text-muted-foreground">Cargando conceptos…</p>;
  }
  if (grupos.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin conceptos para esta búsqueda.</p>;
  }
  return (
    <div className="flex flex-col gap-6">
      {grupos.map((grupo) => (
        <div key={grupo.nombre} className="flex flex-col gap-3">
          <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            {grupo.nombre}
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {grupo.entradas.map(([clave, entrada]) => (
              <Card key={clave}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">{entrada.etiqueta}</CardTitle>
                </CardHeader>
                <CardContent className="pt-0 text-sm text-muted-foreground">
                  {entrada.definicion}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
