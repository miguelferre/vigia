/** Selectores de clase del lanzador de explicaciones, global y local. */

import { CLASE_POR_DEFECTO, SelectorClaseExplicacion } from "./clase-explicada";

interface Props {
  clases: string[];
  favorables: string[];
  valor: string;
  onChange: (v: string) => void;
}

export { CLASE_POR_DEFECTO };

export function ClaseGlobal({ clases, favorables, valor, onChange }: Props) {
  return (
    <SelectorClaseExplicacion
      id="clase-global"
      etiqueta="Clase a explicar (global)"
      porDefecto={`Conjunto favorable${favorables.length > 0 ? ` (${favorables.join(", ")})` : ""}`}
      clases={clases}
      valor={valor}
      onChange={onChange}
      ayuda="Por defecto explica la probabilidad del conjunto favorable. Elige una clase para ver qué variables la mueven."
    />
  );
}

export function ClaseLocal({ clases, valor, onChange }: Omit<Props, "favorables">) {
  return (
    <SelectorClaseExplicacion
      id="clase-local"
      etiqueta="Clase a explicar (local)"
      porDefecto="La clase predicha para la fila"
      clases={clases}
      valor={valor}
      onChange={onChange}
      ayuda="Por defecto explica la clase que predijo el modelo. Salen las probabilidades de todas las clases."
    />
  );
}
