/**
 * Diapositiva 6: lo que el Reglamento de IA pide a quien despliega (vigilar,
 * supervisión humana competente, registros). Sin fechas en la figura.
 */

import { Figura, Tx, Rc, Ci, Ic, Medalla } from "./primitivas";

const ETIQUETA =
  "La ley ya lo exige a quien despliega. El Reglamento de IA pide a quien despliega vigilar el funcionamiento, garantizar supervisión humana competente y conservar registros.";

export function D06({ className }: { className?: string }) {
  return (
    <Figura className={className} etiqueta={ETIQUETA}>
      <Rc x={8} y={24} w={584} h={372} c="v" f="v" r={14} sw={2} />
      <Medalla x={56} y={76} n="shield" />
      <Tx x={100} y={86} s={24} w={700} c="v">Reglamento de IA</Tx>
      <Tx x={100} y={112} w={500} c="mu">lo que pide a quien despliega</Tx>
      <Ci x={108} y={220} r={44} c="v" sw={2} />
      <Ic n="eye" x={86} y={198} z={44} c="v" sw={2.2} />
      <Tx x={108} y={300} s={19} w={600} a="middle">Vigila el</Tx>
      <Tx x={108} y={324} s={19} w={600} a="middle">funcionamiento</Tx>
      <Ci x={300} y={220} r={44} c="v" sw={2} />
      <Ic n="users" x={278} y={198} z={44} c="v" sw={2.2} />
      <Tx x={300} y={300} s={19} w={600} a="middle">Supervisión humana</Tx>
      <Tx x={300} y={324} s={19} w={600} a="middle">competente</Tx>
      <Ci x={492} y={220} r={44} c="v" sw={2} />
      <Ic n="doc" x={470} y={198} z={44} c="v" sw={2.2} />
      <Tx x={492} y={300} s={19} w={600} a="middle">Conserva</Tx>
      <Tx x={492} y={324} s={19} w={600} a="middle">registros</Tx>
    </Figura>
  );
}

export default D06;
