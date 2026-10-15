/**
 * Diapositiva 2: el modelo no cambia y la población sí. Datos de entrenamiento
 * fijos y población real que cambia; con el tiempo la línea del modelo queda
 * plana y la de la población se aleja.
 */

import { Figura, Tx, Rc, Ci, Tr } from "./primitivas";

const ETIQUETA =
  "El modelo no cambia y la población sí. Los datos de entrenamiento son fijos y la población real cambia; con el tiempo la línea del modelo queda plana y la de la población se aleja.";

export function D02({ className }: { className?: string }) {
  return (
    <Figura className={className} etiqueta={ETIQUETA}>
      <Rc x={16} y={16} w={224} h={64} c="v" />
      <Tx x={128} y={44} s={17} w={600} a="middle">Datos de entrenamiento</Tx>
      <Tx x={128} y={66} s={14} c="mu" a="middle">fijos</Tx>
      <Rc x={360} y={16} w={224} h={64} c="t" />
      <Tx x={472} y={44} s={17} w={600} a="middle">Población real</Tx>
      <Tx x={472} y={66} s={14} c="mu" a="middle">cambia</Tx>
      <Tr d="M240 48H358" m="i" />
      <Tx x={300} y={72} s={14} w={500} c="mu" a="middle">decide sobre</Tx>
      <Tr d="M56 176H540L540 312L480 322L420 300L360 262L300 222L240 196L170 200L110 192L56 176Z" c="none" f="m" />
      <Tr d="M56 176H540" c="v" sw={3.5} />
      <Ci x={540} y={176} r={6} c="v" solid />
      <Tr d="M56 176L110 192L170 200L240 196L300 222L360 262L420 300L480 322L540 312" c="t" sw={3.5} />
      <Ci x={540} y={312} r={6} c="t" solid />
      <Tx x={540} y={160} s={17} w={600} c="v" a="end">modelo</Tx>
      <Tx x={540} y={340} s={17} w={600} c="t" a="end">población real</Tx>
      <Tx x={440} y={226} w={600} c="m" a="middle">deja de acertar</Tx>
    </Figura>
  );
}

export default D02;
