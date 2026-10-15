/**
 * Diapositiva 3: tres monitores (equidad, calidad, deriva), cada uno con lo
 * que mide y la pregunta que responde, y debajo un dibujo mínimo de cada uno.
 */

import { Figura, Tx, Rc, Ci, Tr, Medalla, Barra } from "./primitivas";

const ETIQUETA =
  "Tres monitores. Equidad, calidad y deriva: cada monitor mide una cosa y responde una pregunta.";

export function D03({ className }: { className?: string }) {
  return (
    <Figura className={className} etiqueta={ETIQUETA}>
      <Rc x={8} y={24} w={184} h={372} c="m" f="m" r={10} sw={2} />
      <Medalla x={100} y={80} n="scale" c="m" />
      <Tx x={100} y={140} s={22} w={700} c="m" a="middle">Equidad</Tx>
      <Tx x={100} y={166} s={15} c="mu" a="middle">Trato entre grupos</Tx>
      <Tx x={100} y={344} s={17} w={700} a="middle">¿Trata distinto a</Tx>
      <Tx x={100} y={366} s={17} w={700} a="middle">un grupo?</Tx>
      <Rc x={208} y={24} w={184} h={372} c="t" f="t" r={10} sw={2} />
      <Medalla x={300} y={80} n="check" c="t" />
      <Tx x={300} y={140} s={22} w={700} c="t" a="middle">Calidad</Tx>
      <Tx x={300} y={166} s={15} c="mu" a="middle">Acierto frente a</Tx>
      <Tx x={300} y={186} s={15} c="mu" a="middle">la etiqueta real</Tx>
      <Tx x={300} y={344} s={17} w={700} a="middle">¿Acierta menos</Tx>
      <Tx x={300} y={366} s={17} w={700} a="middle">que antes?</Tx>
      <Rc x={408} y={24} w={184} h={372} c="v" f="v" r={10} sw={2} />
      <Medalla x={500} y={80} n="chart" />
      <Tx x={500} y={140} s={22} w={700} c="v" a="middle">Deriva</Tx>
      <Tx x={500} y={166} s={15} c="mu" a="middle">Parecido con</Tx>
      <Tx x={500} y={186} s={15} c="mu" a="middle">la línea base</Tx>
      <Tx x={500} y={344} s={17} w={700} a="middle">¿Han cambiado</Tx>
      <Tx x={500} y={366} s={17} w={700} a="middle">los datos?</Tx>
      <Barra x={34} y={242} w={26} h={52} r={3} c="mu" />
      <Tx x={47} y={312} s={13} w={700} c="mu" a="middle">A</Tx>
      <Barra x={68} y={248} w={26} h={46} r={3} c="mu" />
      <Tx x={81} y={312} s={13} w={700} c="mu" a="middle">B</Tx>
      <Barra x={102} y={272} w={26} h={22} r={3} c="m" />
      <Tx x={115} y={312} s={13} w={700} c="m" a="middle">C</Tx>
      <Barra x={136} y={244} w={26} h={50} r={3} c="mu" />
      <Tx x={149} y={312} s={13} w={700} c="mu" a="middle">D</Tx>
      <Tr d="M240 214L280 224L320 240L356 268" c="t" sw={3} />
      <Ci x={356} y={268} r={5} c="m" solid />
      <Tr d="M236 252H364" c="m" sw={1.5} dash="4 4" />
      <Tr d="M464 290C482 290 486 232 506 232S526 290 550 290" c="v" f="v" sw={3} />
      <Tr d="M436 290C452 290 456 232 474 232S494 290 514 290" dash="5 4" />
    </Figura>
  );
}

export default D03;
