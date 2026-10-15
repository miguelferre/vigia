/**
 * Diapositiva 8: la capa técnica y la capa humana convergen en una conclusión
 * mejor, de la que salen tres acciones.
 */

import { Figura, Tx, Rc, Tr, Ic } from "./primitivas";

const ETIQUETA =
  "Dos capas, una conclusión. La capa técnica y la capa humana convergen en una conclusión mejor, de la que salen tres acciones: problema del modelo, problema de uso o sin problema.";

export function D08({ className }: { className?: string }) {
  return (
    <Figura className={className} etiqueta={ETIQUETA}>
      <Tr d="M156 190V214H300V236" sw={2.5} m="i" />
      <Tr d="M444 190V214H300" sw={2.5} />
      <Tr d="M300 280V300H92V320" sw={2.5} m="m" />
      <Tr d="M300 280V320" sw={2.5} m="v" />
      <Tr d="M300 300H508V320" sw={2.5} m="t" />
      <Rc x={24} y={12} w={264} h={178} c="v" f="v" r={12} sw={2} />
      <Tx x={156} y={44} s={20} w={700} c="v" a="middle">Capa técnica</Tx>
      <Ic n="scale" x={52} y={66} z={22} c="v" sw={2} />
      <Tx x={84} y={83} w={500}>equidad</Tx>
      <Ic n="check" x={52} y={106} z={22} c="v" sw={2} />
      <Tx x={84} y={123} w={500}>calidad</Tx>
      <Ic n="chart" x={52} y={146} z={22} c="v" sw={2} />
      <Tx x={84} y={163} w={500}>deriva</Tx>
      <Rc x={312} y={12} w={264} h={178} c="t" f="t" r={12} sw={2} />
      <Tx x={444} y={44} s={20} w={700} c="t" a="middle">Capa humana</Tx>
      <Ic n="pencil" x={340} y={66} z={22} c="t" sw={2} />
      <Tx x={372} y={83} w={500}>correcciones</Tx>
      <Ic n="bell" x={340} y={106} z={22} c="t" sw={2} />
      <Tx x={372} y={123} w={500}>notificaciones</Tx>
      <Ic n="pulse" x={340} y={146} z={22} c="t" sw={2} />
      <Tx x={372} y={163} w={500}>uso</Tx>
      <Rc x={204} y={236} w={192} h={44} c="v" f="v" r={10} sw={2.5} />
      <Tx x={300} y={264} s={17} w={700} a="middle">Una conclusión mejor</Tx>
      <Rc x={8} y={320} w={184} h={88} c="m" f="m" r={10} sw={2} />
      <Tx x={100} y={352} w={700} c="m" a="middle">Problema del modelo</Tx>
      <Tx x={100} y={378} s={14} w={500} c="mu" a="middle">contener, reequilibrar</Tx>
      <Rc x={208} y={320} w={184} h={88} c="v" f="v" r={10} sw={2} />
      <Tx x={300} y={352} w={700} c="v" a="middle">Problema de uso</Tx>
      <Tx x={300} y={378} s={14} w={500} c="mu" a="middle">formación, protocolo</Tx>
      <Rc x={408} y={320} w={184} h={88} c="t" f="t" r={10} sw={2} />
      <Tx x={500} y={352} w={700} c="t" a="middle">Sin problema</Tx>
      <Tx x={500} y={378} s={14} w={500} c="mu" a="middle">seguir vigilando</Tx>
    </Figura>
  );
}

export default D08;
