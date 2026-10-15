/**
 * Diapositiva 7: Tu entorno, Vigía en local y la salida, dentro de un marco
 * que dice que nada sale del equipo; debajo, qué viaja y qué no.
 */

import { Figura, Tx, Rc, Tr, Ic } from "./primitivas";

const ETIQUETA =
  "Vigía en local. Tu entorno, Vigía en local y la salida, dentro de un marco que dice que nada sale del equipo; viajan salidas y variables desidentificadas y no viajan los datos identificativos.";

export function D07({ className }: { className?: string }) {
  return (
    <Figura className={className} etiqueta={ETIQUETA}>
      <Rc x={4} y={16} w={592} h={292} c="mu" r={14} dash="7 5" />
      <Ic n="lock" x={18} y={26} z={20} c="mu" sw={2} />
      <Tx x={44} y={42} s={15} w={600} c="mu">Tu equipo</Tx>
      <Tr d="M176 174H222" sw={2.5} m="i" />
      <Tr d="M376 174H422" sw={2.5} m="v" />
      <Rc x={20} y={68} w={156} h={212} r={10} sw={2} />
      <Tx x={98} y={98} s={18} w={700} a="middle">Tu entorno</Tx>
      <Tx x={98} y={130} s={14} w={500} a="middle">Modelo en</Tx>
      <Tx x={98} y={152} s={14} w={500} a="middle">producción,</Tx>
      <Tx x={98} y={174} s={14} w={500} a="middle">no se toca</Tx>
      <Tx x={98} y={218} s={14} w={500} a="middle">Datos para medir</Tx>
      <Tx x={98} y={262} s={14} w={500} a="middle">Registro de uso</Tx>
      <Rc x={224} y={68} w={152} h={212} c="v" f="v" r={10} sw={2} />
      <Tx x={300} y={98} s={18} w={700} c="v" a="middle">Vigía, en local</Tx>
      <Tx x={300} y={130} s={14} w={500} a="middle">Línea base</Tx>
      <Tx x={300} y={174} s={14} w={500} a="middle">4 monitores</Tx>
      <Tx x={300} y={218} s={14} w={500} a="middle">Capa humana</Tx>
      <Tx x={300} y={262} s={14} w={500} a="middle">Diario</Tx>
      <Rc x={424} y={68} w={152} h={212} c="t" r={10} sw={2} />
      <Tx x={500} y={98} s={18} w={700} c="t" a="middle">Salida</Tx>
      <Tx x={500} y={130} s={14} w={500} a="middle">Cuadro de mando</Tx>
      <Tx x={500} y={174} s={14} w={500} a="middle">Alertas</Tx>
      <Tx x={500} y={218} s={14} w={500} a="middle">Diario</Tx>
      <Tx x={500} y={240} s={14} w={500} a="middle">exportable</Tx>
      <Rc x={4} y={332} w={296} h={76} c="v" f="v" r={10} />
      <Tx x={18} y={358} w={700} c="v">Qué viaja</Tx>
      <Tx x={18} y={382} s={15} w={500}>salidas y variables,</Tx>
      <Tx x={18} y={400} s={15} w={500}>desidentificadas</Tx>
      <Rc x={310} y={332} w={286} h={76} c="m" f="m" r={10} />
      <Ic n="lock" x={324} y={342} z={20} c="m" sw={2} />
      <Tx x={350} y={358} w={700} c="m">Qué no viaja</Tx>
      <Tx x={324} y={386} s={15} w={500}>los datos identificativos</Tx>
    </Figura>
  );
}

export default D07;
