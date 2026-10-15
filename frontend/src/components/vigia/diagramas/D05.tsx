/**
 * Diapositiva 5: con y sin vigilancia sobre una misma línea de tiempo; con
 * vigilancia la alerta salta en la semana 1, sin ella la detección es externa
 * y tarda meses.
 */

import { Figura, Tx, Rc, Ci, Tr, Medalla } from "./primitivas";

const ETIQUETA =
  "Con y sin vigilancia. Con vigilancia la alerta salta en la semana 1 y los afectados son decenas; sin vigilancia la detección es externa, meses después, y los afectados son cientos o miles.";

export function D05({ className }: { className?: string }) {
  return (
    <Figura className={className} etiqueta={ETIQUETA}>
      <Tx x={40} y={28} s={20} w={700} c="t">Con vigilancia</Tx>
      <Tr d="M40 112H570" c="t" sw={3} />
      <Ci x={96} y={112} r={6} c="t" solid />
      <Medalla x={96} y={72} n="alert" c="t" r={20} z={22} />
      <Tx x={126} y={78} s={17} w={600} c="t">alerta: semana 1</Tx>
      <Rc x={96} y={134} w={40} h={16} c="t" f="t" r={4} />
      <Tx x={148} y={148} w={500}>afectados: decenas</Tx>
      <Tx x={40} y={224} s={20} w={700} c="m">Sin vigilancia</Tx>
      <Tr d="M40 290H570" c="m" sw={3} />
      <Ci x={96} y={290} r={6} c="m" solid />
      <Ci x={520} y={290} r={6} c="m" solid />
      <Medalla x={520} y={252} n="search" c="m" r={20} z={22} />
      <Tx x={488} y={250} w={600} c="m" a="end">detección externa:</Tx>
      <Tx x={488} y={270} w={600} c="m" a="end">meses después</Tx>
      <Rc x={96} y={312} w={424} h={16} c="m" f="m" r={4} />
      <Tx x={520} y={356} w={500} a="end">afectados: cientos o miles</Tx>
      <Tr d="M40 398H570" sw={1.5} m="i" />
      <Tx x={570} y={388} s={14} w={500} c="mu" a="end">tiempo</Tx>
    </Figura>
  );
}

export default D05;
